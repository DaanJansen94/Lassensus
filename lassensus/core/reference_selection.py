#!/usr/bin/env python3

import os
import subprocess
import sys
from pathlib import Path
import argparse
import logging
import shutil
import json
import gzip
import multiprocessing
from datetime import datetime

def setup_logging(output_dir):
    """Set up logging configuration."""
    log_file = Path(output_dir) / 'lassensus.log'
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = logging.getLogger(__name__)

def get_cpu_count():
    """Get the number of available CPU cores."""
    try:
        # Get the number of CPU cores
        cpu_count = multiprocessing.cpu_count()
        # Use all cores except one to leave some system resources free
        threads = max(1, cpu_count - 1)
        logger.info(f"Using {threads} CPU cores (out of {cpu_count} available)")
        return threads
    except Exception as e:
        logger.warning(f"Could not determine CPU count, using default of 4 cores: {e}")
        return 4

def count_reads(fastq_file):
    """Count the number of reads in a FASTQ file."""
    try:
        cmd = ['zcat', str(fastq_file), '|', 'wc', '-l']
        result = subprocess.run(' '.join(cmd), shell=True, capture_output=True, text=True, check=True)
        return int(result.stdout.strip()) // 4  # Divide by 4 as each read has 4 lines
    except subprocess.CalledProcessError as e:
        logger.error(f"Error counting reads in {fastq_file}: {e}")
        sys.exit(1)

def setup_directories(output_dir):
    """Create and return required directories."""
    # Convert to Path if not already
    output_dir = Path(output_dir)
    
    # Get tool directory
    tool_dir = Path(__file__).parent.parent.parent
    
    # Check if output directory is inside tool directory
    if output_dir.is_relative_to(tool_dir):
        logger.error("Output directory cannot be inside the tool directory")
        sys.exit(1)
    
    # Create required directories
    dirs = {
        'references': output_dir / 'references',
        'selection_best_references': output_dir / 'references' / 'selection_best_references'
    }
    
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created directory: {d}")
    
    return dirs

def download_references(output_dir, genome=1, completeness=90, host=4, metadata=4):
    """Download Lassa virus references using lassaseq.
    
    Args:
        output_dir: Directory to save references
        genome: Genome completeness filter (1=complete only, 2=partial, 3=no filter)
        completeness: Minimum sequence completeness (1-100) when genome=2
        host: Host filter (1=human, 2=rodent, 3=both, 4=no filter)
        metadata: Metadata filter (1=known location, 2=known date, 3=both, 4=no filter)
    """
    logger.info("Downloading Lassa virus references...")
    logger.info(f"Using parameters: genome={genome}, completeness={completeness}%, host={host}, metadata={metadata}")
    
    cmd = [
        'lassaseq',
        '-o', output_dir,
        '--genome', str(genome),
        '--host', str(host),
        '--metadata', str(metadata)
    ]
    
    if genome == 2:
        cmd.extend(['--completeness', str(completeness)])
    
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info("Successfully downloaded references")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error downloading references: {e.stderr}")
        sys.exit(1)

def get_reference_info(ref_file):
    """Extract information from reference FASTA header."""
    references = []
    current_ref = None
    current_seq = []
    
    with open(ref_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('>'):
                # Save previous reference if exists
                if current_ref:
                    references.append({
                        'accession': current_ref['accession'],
                        'description': current_ref['description'],
                        'sequence': ''.join(current_seq)
                    })
                
                # Start new reference
                header = line[1:]
                fields = header.split()
                current_ref = {
                    'accession': fields[0],
                    'description': ' '.join(fields[1:])
                }
                current_seq = []
            else:
                current_seq.append(line)
    
    # Add the last reference
    if current_ref:
        references.append({
            'accession': current_ref['accession'],
            'description': current_ref['description'],
            'sequence': ''.join(current_seq)
        })
    
    return references

def get_reference_files(references_dir):
    """Get all reference files from segment-specific directories."""
    reference_files = []
    fasta_dir = os.path.join(references_dir, 'FASTA')
    
    # Look in L and S segment directories
    for segment in ['L_segment', 'S_segment']:
        segment_dir = os.path.join(fasta_dir, segment)
        if os.path.exists(segment_dir):
            for ext in ['*.fasta', '*.fa']:
                for ref_file in Path(segment_dir).glob(ext):
                    references = get_reference_info(ref_file)
                    for ref in references:
                        reference_files.append((ref_file, ref))
    
    return reference_files

def find_best_reference(sample_fastq, references_dir, output_dir):
    """Find the best matching reference for a sample using minimap2."""
    logger.info(f"Finding best reference for {sample_fastq}")
    
    # Get all reference files with their info
    reference_files = get_reference_files(references_dir)
    
    if not reference_files:
        logger.error(f"No reference files found in {references_dir}")
        sys.exit(1)
    
    logger.info(f"Found {len(reference_files)} reference sequences")
    
    # Get number of CPU cores to use
    threads = get_cpu_count()
    
    # Track statistics for all references by segment
    segment_stats = {'L': [], 'S': []}
    best_refs = {'L': None, 'S': None}
    best_coverage = {'L': 0, 'S': 0}
    best_stats = {'L': None, 'S': None}
    
    # Create temporary directory for this sample
    sample_name = Path(sample_fastq).stem.split('_rarefied')[0]
    temp_dir = Path(output_dir) / 'references' / 'selection_best_references' / sample_name / 'temp'
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    for ref_file, ref_info in reference_files:
        # Determine segment from file path
        segment = 'L' if 'L_segment' in str(ref_file) else 'S'
        
        # Create temporary FASTA with just this reference
        temp_fasta = temp_dir / f"temp_{ref_info['accession']}.fasta"
        with open(temp_fasta, 'w') as f:
            f.write(f">{ref_info['accession']} {ref_info['description']}\n")
            f.write(ref_info['sequence'] + "\n")
        
        # Run minimap2
        output_sam = temp_dir / f"{Path(sample_fastq).stem}_{ref_info['accession']}.sam"
        minimap_cmd = [
            'minimap2',
            '-ax', 'map-ont',  # Nanopore preset
            '-t', str(threads), # Use available CPU cores
            str(temp_fasta),
            str(sample_fastq)
        ]
        
        try:
            with open(output_sam, 'w') as f:
                subprocess.run(minimap_cmd, check=True, stdout=f, stderr=subprocess.PIPE, text=True)
            
            # Calculate mapping statistics
            stats = calculate_mapping_stats(output_sam)
            stats.update(ref_info)  # Add reference info to stats
            
            segment_stats[segment].append(stats)
            
            if stats['mapped_reads'] > best_coverage[segment]:
                best_coverage[segment] = stats['mapped_reads']
                best_refs[segment] = {
                    'file': str(ref_file),
                    'accession': ref_info['accession'],
                    'description': ref_info['description']
                }
                best_stats[segment] = stats
            
            # Clean up temporary files
            os.remove(temp_fasta)
            os.remove(output_sam)
            
        except subprocess.CalledProcessError as e:
            logger.warning(f"Error aligning to {ref_info['accession']}: {e.stderr}")
            os.remove(temp_fasta)
            continue
    
    # Clean up temporary directory
    shutil.rmtree(temp_dir)
    
    return best_refs, best_stats, segment_stats

def calculate_mapping_stats(sam_file):
    """Calculate mapping statistics from SAM file."""
    mapped_reads = 0
    total_length = 0
    total_matches = 0
    
    with open(sam_file, 'r') as f:
        for line in f:
            if line.startswith('@'):
                continue
            
            fields = line.strip().split('\t')
            if len(fields) < 11:
                continue
                
            flag = int(fields[1])
            if flag & 0x4:  # unmapped
                continue
                
            mapped_reads += 1
            
            # Parse CIGAR string for alignment statistics
            cigar = fields[5]
            matches = sum(int(n) for n in ''.join(c if c.isdigit() else ' ' for c in cigar).split())
            total_length += matches
            
            # Calculate identity from optional NM field
            for field in fields[11:]:
                if field.startswith('NM:i:'):
                    nm = int(field.split(':')[2])
                    total_matches += matches - nm
                    break
    
    stats = {
        'mapped_reads': mapped_reads,
        'coverage': total_length / 1000,  # Approximate coverage
        'avg_identity': (total_matches / total_length * 100) if total_length > 0 else 0
    }
    
    return stats

def rarefy_all_samples(samples, input_dir, output_dir, n_reads=10000):
    """Rarefy all samples to specified number of reads."""
    logger.info(f"\nRarefying all samples to {n_reads:,} reads...")
    rarefied_files = {}
    
    for sample in samples:
        input_file = input_dir / f"{sample}.fastq.gz"
        total_reads = count_reads(input_file)
        logger.info(f"\nProcessing {sample}:")
        logger.info(f"Total reads: {total_reads:,}")
        
        # Create sample-specific directory in selection_best_references
        sample_dir = output_dir / 'references' / 'selection_best_references' / sample
        sample_dir.mkdir(parents=True, exist_ok=True)
        
        # Create rarefied FASTQ
        rarefied_file = sample_dir / f"{sample}_rarefied.fastq.gz"
        rarefy_reads(input_file, rarefied_file, n_reads)
        logger.info(f"Created rarefied FASTQ with {n_reads:,} reads")
        
        rarefied_files[sample] = {
            'rarefied_file': rarefied_file,
            'total_reads': total_reads
        }
    
    return rarefied_files

def process_sample(sample, rarefied_info, references_dir, output_dir, min_identity):
    """Process a single sample to find the best reference."""
    logger.info(f"\nProcessing sample: {sample}")
    
    # Map rarefied reads to references
    best_refs, best_stats, segment_stats = find_best_reference(
        rarefied_info['rarefied_file'],
        references_dir,
        output_dir / sample
    )
    
    # Save results including total read count
    save_results(sample, best_refs, best_stats, segment_stats, rarefied_info['total_reads'], output_dir)
    
    return best_refs

def rarefy_reads(input_file, output_file, n_reads):
    """Rarefy FASTQ file to specified number of reads."""
    try:
        # Use seqtk to randomly sample reads
        cmd = ['seqtk', 'sample', '-s', '42', str(input_file), str(n_reads)]
        with open(output_file, 'w') as f:
            subprocess.run(cmd, stdout=f, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error rarefying reads: {e}")
        sys.exit(1)

def save_results(sample, best_refs, best_stats, segment_stats, total_reads, output_dir):
    """Save mapping statistics and best reference to JSON file and save best reference sequences as FASTA."""
    results = {
        'sample': sample,
        'total_reads': total_reads,
        'rarefied_reads': 10000,
        'best_references': best_refs,
        'best_stats': best_stats,
        'segment_stats': segment_stats
    }
    
    # Save everything in the sample's directory
    sample_dir = Path(output_dir) / 'references' / 'selection_best_references' / sample
    sample_dir.mkdir(parents=True, exist_ok=True)
    
    # Save JSON results in sample directory
    json_file = sample_dir / f"{sample}_reference_selection.json"
    with open(json_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Save best reference sequences as FASTA in sample directory
    for segment in ['L', 'S']:
        if best_refs[segment]:
            # Read the original reference file
            ref_file = Path(best_refs[segment]['file'])
            fasta_file = sample_dir / f"{sample}_{segment}_best_reference.fasta"
            
            # Extract only the best reference sequence
            with open(ref_file, 'r') as f_in, open(fasta_file, 'w') as f_out:
                write_sequence = False
                for line in f_in:
                    if line.startswith('>'):
                        # Check if this is our best reference
                        if best_refs[segment]['accession'] in line:
                            write_sequence = True
                            f_out.write(line)
                        else:
                            write_sequence = False
                    elif write_sequence:
                        f_out.write(line)
            
            logger.info(f"Saved best {segment}-segment reference sequence to {fasta_file}")
    
    logger.info(f"Saved results to {json_file}")

def find_samples(input_dir):
    """Find all FASTQ samples in input directory."""
    input_dir = Path(input_dir)
    fastq_files = list(input_dir.glob('*.fastq.gz'))
    return [f.stem.split('.')[0] for f in fastq_files]

def setup_consensus_directories(output_dir, samples, input_dir):
    """Set up directories for consensus generation."""
    consensus_dir = output_dir / 'consensus'
    consensus_dir.mkdir(exist_ok=True)
    
    for sample in samples:
        # Create sample directory
        sample_dir = consensus_dir / sample
        sample_dir.mkdir(exist_ok=True)
        
        # Copy reference files
        ref_dir = output_dir / 'references' / 'selection_best_references' / sample
        l_ref = ref_dir / f"{sample}_L_best_reference.fasta"
        s_ref = ref_dir / f"{sample}_S_best_reference.fasta"
        
        if l_ref.exists():
            shutil.copy2(l_ref, sample_dir / f"{sample}_L_reference.fasta")
            logger.info(f"Copied L-segment reference for {sample}")
        
        if s_ref.exists():
            shutil.copy2(s_ref, sample_dir / f"{sample}_S_reference.fasta")
            logger.info(f"Copied S-segment reference for {sample}")
        
        # Copy FASTQ file
        fastq_file = input_dir / f"{sample}.fastq.gz"
        if fastq_file.exists():
            shutil.copy2(fastq_file, sample_dir / f"{sample}.fastq.gz")
            logger.info(f"Copied FASTQ file for {sample}")
    
    return consensus_dir

def main(args=None):
    """Main function for reference selection."""
    if args is None:
        # If called directly as a script, set up argument parser
        parser = argparse.ArgumentParser(description='Select reference sequences for Lassa virus samples')
        parser.add_argument('--input_dir', required=True, help='Directory containing input FASTQ files')
        parser.add_argument('--output_dir', required=True, help='Directory for pipeline output')
        parser.add_argument('--min_identity', type=float, default=90.0, help='Minimum identity percentage to include in results (default: 90.0)')
        parser.add_argument('--genome', type=int, choices=[1,2,3], default=2,
            help='Genome completeness filter: 1=complete only (>99%), 2=partial (specify --completeness), 3=no filter (default: 2)')
        parser.add_argument('--completeness', type=int, default=90,
            help='Minimum sequence completeness (1-100) when --genome=2 (default: 90)')
        parser.add_argument('--host', type=int, choices=[1,2,3,4], default=4,
            help='Host filter: 1=human, 2=rodent, 3=both, 4=no filter (default: 4)')
        parser.add_argument('--metadata', type=int, choices=[1,2,3,4], default=4,
            help='Metadata filter: 1=known location, 2=known date, 3=both, 4=no filter (default: 4)')
        args = parser.parse_args()
    
    # Convert input and output directories to Path objects
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    
    # Create output directories
    dirs = setup_directories(output_dir)
    
    # Set up logging
    setup_logging(output_dir)
    
    # Find input samples
    samples = find_samples(input_dir)
    if not samples:
        logger.error("No samples found in input directory")
        sys.exit(1)
    
    logger.info(f"\nFound {len(samples)} samples to process:")
    total_reads = 0
    for i, sample in enumerate(samples, 1):
        read_count = count_reads(input_dir / f"{sample}.fastq.gz")
        total_reads += read_count
        logger.info(f"{i}. {sample} ({read_count:,} reads)")
    logger.info(f"Total reads across all samples: {total_reads:,}")
    
    logger.info(f"\nOutput will be saved to: {output_dir}")
    logger.info(f"Minimum identity threshold: {args.min_identity}%")
    
    # First, rarefy all samples
    rarefied_files = rarefy_all_samples(samples, input_dir, output_dir)
    
    # Download references once for all samples
    logger.info("\nDownloading references for all samples...")
    download_references(
        dirs['references'],
        genome=args.genome,
        completeness=args.completeness,
        host=args.host,
        metadata=args.metadata
    )
    
    # Process each sample using rarefied reads
    logger.info("\nFinding best references for each sample...")
    for sample in samples:
        best_refs = process_sample(
            sample,
            rarefied_files[sample],
            dirs['references'],
            output_dir,
            args.min_identity
        )
        for segment in ['L', 'S']:
            if best_refs[segment]:
                logger.info(f"Best {segment}-segment reference for {sample}: {best_refs[segment]['accession']}")
    
    # Clean up empty directories
    for sample in samples:
        empty_dir = output_dir / sample
        if empty_dir.exists():
            shutil.rmtree(empty_dir)
    
    # Set up consensus directories
    consensus_dir = setup_consensus_directories(output_dir, samples, input_dir)
    
    logger.info("\nReference selection complete!")
    logger.info(f"Results saved in: {dirs['selection_best_references']}")
    logger.info(f"Consensus directories set up in: {consensus_dir}")

if __name__ == '__main__':
    main() 
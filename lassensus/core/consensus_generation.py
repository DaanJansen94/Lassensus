#!/usr/bin/env python3

import os
import subprocess
import sys
from pathlib import Path
import argparse
import logging
import shutil
import multiprocessing

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

def check_dependencies():
    """Check if required tools are installed and install missing ones."""
    dependencies = ['minimap2', 'samtools', 'ivar']
    missing = []
    
    for tool in dependencies:
        if shutil.which(tool) is None:
            missing.append(tool)
    
    if missing:
        logger.info(f"Missing dependencies: {', '.join(missing)}")
        logger.info("Installing missing dependencies...")
        
        # Install ivar if missing
        if 'ivar' in missing:
            try:
                subprocess.run(['conda', 'install', '-y', 'bioconda::ivar'], check=True)
                logger.info("Successfully installed ivar")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to install ivar: {e}")
                sys.exit(1)
        
        # Check again after installation
        if shutil.which('ivar') is None:
            logger.error("Failed to install ivar. Please install manually: conda install -y bioconda::ivar")
            sys.exit(1)

def map_reads(fastq_file, reference_file, output_dir, sample_name, segment):
    """Map reads to reference using minimap2."""
    logger.info(f"Mapping reads to {segment}-segment reference for {sample_name}")
    
    # Create output files
    bam_file = output_dir / f"{sample_name}_{segment}.bam"
    sorted_bam = output_dir / f"{sample_name}_{segment}.sorted.bam"
    
    # Run minimap2
    minimap_cmd = [
        'minimap2',
        '-ax', 'map-ont',
        '-Y',  # Preserve soft-clipped bases
        '-L',  # Output CIGAR strings for long insertions/deletions
        '-t', str(get_cpu_count()),
        str(reference_file),
        str(fastq_file)
    ]
    
    # Pipe minimap2 output to samtools for BAM conversion
    samtools_cmd = [
        'samtools', 'view',
        '-b',  # Output BAM
        '-o', str(bam_file)
    ]
    
    try:
        # Run minimap2 and pipe to samtools
        minimap_process = subprocess.Popen(minimap_cmd, stdout=subprocess.PIPE)
        subprocess.run(samtools_cmd, stdin=minimap_process.stdout, check=True)
        minimap_process.wait()
        
        # Sort BAM file
        subprocess.run([
            'samtools', 'sort',
            '-o', str(sorted_bam),
            str(bam_file)
        ], check=True)
        
        # Index sorted BAM
        subprocess.run([
            'samtools', 'index',
            str(sorted_bam)
        ], check=True)
        
        # Remove unsorted BAM
        os.remove(bam_file)
        
        return sorted_bam
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error mapping reads: {e}")
        sys.exit(1)

def generate_consensus(bam_file, reference_file, output_dir, sample_name, segment, min_depth=50, min_quality=30, majority_threshold=0.7):
    """Generate consensus sequence using ivar."""
    logger.info(f"Generating consensus for {segment}-segment of {sample_name}")
    
    # Create output files
    consensus_file = output_dir / f"{sample_name}_{segment}_consensus.fasta"
    quality_file = output_dir / f"{sample_name}_{segment}_quality.txt"
    
    # Create a temporary prefix for ivar output
    temp_prefix = output_dir / f"{sample_name}_{segment}"
    
    try:
        # First run samtools mpileup
        mpileup_cmd = [
            'samtools', 'mpileup',
            '-aa',  # Output all positions
            '-d', '0',  # No depth limit
            '-Q', '0',  # No base quality threshold
            '-f', str(reference_file),
            str(bam_file)
        ]
        
        # Then pipe to ivar consensus
        ivar_cmd = [
            'ivar', 'consensus',
            '-p', str(temp_prefix),  # Use temporary prefix
            '-m', str(min_depth),  # Minimum depth
            '-q', str(min_quality),  # Minimum quality
            '-t', str(majority_threshold),  # Majority rule threshold
            '-k'  # Skip regions with depth less than minimum depth
        ]
        
        # Run the pipeline
        mpileup_process = subprocess.Popen(mpileup_cmd, stdout=subprocess.PIPE)
        subprocess.run(ivar_cmd, stdin=mpileup_process.stdout, check=True)
        mpileup_process.wait()
        
        # Check for output files in the correct location
        output_fasta = output_dir / f"{sample_name}_{segment}.fa"
        output_qual = output_dir / f"{sample_name}_{segment}.qual.txt"
        
        if not output_fasta.exists():
            logger.error(f"Expected output file not found: {output_fasta}")
            sys.exit(1)
            
        if not output_qual.exists():
            logger.error(f"Expected output file not found: {output_qual}")
            sys.exit(1)
        
        # Rename output files
        shutil.move(output_fasta, consensus_file)
        shutil.move(output_qual, quality_file)
        
        logger.info(f"Generated consensus sequence: {consensus_file}")
        logger.info(f"Generated quality file: {quality_file}")
        
        return consensus_file, quality_file
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error generating consensus: {e}")
        sys.exit(1)

def calculate_completeness(consensus_file, ref_file, refseq_length):
    """Calculate completeness statistics for a consensus sequence.
    
    Args:
        consensus_file: Path to the consensus sequence file
        ref_file: Path to the selected reference sequence file
        refseq_length: Length of the RefSeq reference
    """
    # Read the consensus sequence
    with open(consensus_file, 'r') as f:
        consensus = ''.join(line.strip() for line in f if not line.startswith('>'))
    
    # Read the selected reference sequence
    with open(ref_file, 'r') as f:
        ref_length = len(''.join(line.strip() for line in f if not line.startswith('>')))
    
    # Calculate statistics
    total_length = len(consensus)
    n_count = consensus.count('N')
    non_n_length = total_length - n_count
    
    # Calculate percentages
    completeness_vs_ref = (non_n_length / ref_length) * 100
    completeness_vs_refseq = (non_n_length / refseq_length) * 100
    
    return {
        'total_length': total_length,
        'n_count': n_count,
        'non_n_length': non_n_length,
        'ref_length': ref_length,
        'completeness_vs_ref': completeness_vs_ref,
        'completeness_vs_refseq': completeness_vs_refseq
    }

def process_sample(sample_dir, sample_name, output_dir, min_depth=50, min_quality=30, majority_threshold=0.7):
    """Process a single sample to generate consensus sequences."""
    logger.info(f"\nProcessing sample: {sample_name}")
    
    # Get input files
    fastq_file = sample_dir / f"{sample_name}.fastq.gz"
    l_ref = sample_dir / f"{sample_name}_L_reference.fasta"
    s_ref = sample_dir / f"{sample_name}_S_reference.fasta"
    
    if not all(f.exists() for f in [fastq_file, l_ref, s_ref]):
        logger.error(f"Missing required files for {sample_name}")
        return
    
    # Process L segment
    l_bam = map_reads(fastq_file, l_ref, sample_dir, sample_name, 'L')
    l_consensus, l_quality = generate_consensus(l_bam, l_ref, sample_dir, sample_name, 'L', 
                                               min_depth, min_quality, majority_threshold)
    
    # Process S segment
    s_bam = map_reads(fastq_file, s_ref, sample_dir, sample_name, 'S')
    s_consensus, s_quality = generate_consensus(s_bam, s_ref, sample_dir, sample_name, 'S',
                                               min_depth, min_quality, majority_threshold)
    
    # Create medaka output directory
    medaka_dir = sample_dir / "medaka_output"
    medaka_dir.mkdir(exist_ok=True)
    
    # Polish L segment with medaka
    logger.info(f"Polishing L segment consensus for {sample_name} with medaka")
    medaka_cmd = [
        'medaka_consensus',
        '-i', str(fastq_file),
        '-d', str(l_consensus),
        '-o', str(medaka_dir),
        '-t', str(get_cpu_count())
    ]
    subprocess.run(medaka_cmd, check=True)
    
    # Move and rename polished L consensus
    l_polished = medaka_dir / "consensus.fasta"
    l_final = sample_dir / f"{sample_name}_L_consensus_polished.fasta"
    shutil.move(l_polished, l_final)
    
    # Polish S segment with medaka
    logger.info(f"Polishing S segment consensus for {sample_name} with medaka")
    medaka_cmd = [
        'medaka_consensus',
        '-i', str(fastq_file),
        '-d', str(s_consensus),
        '-o', str(medaka_dir),
        '-t', str(get_cpu_count())
    ]
    subprocess.run(medaka_cmd, check=True)
    
    # Move and rename polished S consensus
    s_polished = medaka_dir / "consensus.fasta"
    s_final = sample_dir / f"{sample_name}_S_consensus_polished.fasta"
    shutil.move(s_polished, s_final)
    
    # Reference lengths for RefSeq
    refseq_lengths = {
        'L': 7279,  # Reference length for L segment
        'S': 3402   # Reference length for S segment
    }
    
    # Calculate completeness statistics using polished consensus
    l_stats = calculate_completeness(l_final, l_ref, refseq_lengths['L'])
    s_stats = calculate_completeness(s_final, s_ref, refseq_lengths['S'])
    
    # Log completeness statistics
    logger.info(f"\nCompleteness statistics for {sample_name}:")
    logger.info("L segment:")
    logger.info(f"  Total length: {l_stats['total_length']} bp")
    logger.info(f"  N count: {l_stats['n_count']}")
    logger.info(f"  Non-N length: {l_stats['non_n_length']} bp")
    logger.info(f"  Selected reference length: {l_stats['ref_length']} bp")
    logger.info(f"  Completeness vs selected reference: {l_stats['completeness_vs_ref']:.2f}%")
    logger.info(f"  Completeness vs RefSeq: {l_stats['completeness_vs_refseq']:.2f}%")
    
    logger.info("\nS segment:")
    logger.info(f"  Total length: {s_stats['total_length']} bp")
    logger.info(f"  N count: {s_stats['n_count']}")
    logger.info(f"  Non-N length: {s_stats['non_n_length']} bp")
    logger.info(f"  Selected reference length: {s_stats['ref_length']} bp")
    logger.info(f"  Completeness vs selected reference: {s_stats['completeness_vs_ref']:.2f}%")
    logger.info(f"  Completeness vs RefSeq: {s_stats['completeness_vs_refseq']:.2f}%")
    
    logger.info(f"\nGenerated and polished consensus sequences for {sample_name}")
    logger.info(f"L-segment polished consensus: {l_final}")
    logger.info(f"S-segment polished consensus: {s_final}")

    # Remove the medaka_output directory after moving the polished consensus
    if os.path.exists(medaka_dir):
        shutil.rmtree(medaka_dir)
        logger.info(f"Removed temporary medaka output directory: {medaka_dir}")

    # Create AllConsensus directory structure
    all_consensus_dir = os.path.join(output_dir, "AllConsensus")
    l_segment_dir = os.path.join(all_consensus_dir, "L_segment")
    s_segment_dir = os.path.join(all_consensus_dir, "S_segment")
    
    for dir_path in [all_consensus_dir, l_segment_dir, s_segment_dir]:
        os.makedirs(dir_path, exist_ok=True)
    
    # Copy polished consensus files to their respective directories
    shutil.copy2(l_final, l_segment_dir)
    shutil.copy2(s_final, s_segment_dir)
    
    # Create or append to multi-fasta files
    l_multi_fasta = os.path.join(l_segment_dir, "all_L_consensus.fasta")
    s_multi_fasta = os.path.join(s_segment_dir, "all_S_consensus.fasta")
    
    # Append L segment consensus to multi-fasta
    with open(l_multi_fasta, 'a') as outfile:
        with open(l_final, 'r') as infile:
            outfile.write(infile.read())
    
    # Append S segment consensus to multi-fasta
    with open(s_multi_fasta, 'a') as outfile:
        with open(s_final, 'r') as infile:
            outfile.write(infile.read())
    
    logger.info(f"Appended consensus sequences to multi-fasta files in AllConsensus directory")

def main(args=None):
    """Main function for consensus generation."""
    if args is None:
        parser = argparse.ArgumentParser(description='Generate consensus sequences from mapped reads')
        parser.add_argument('--input_dir', required=True, help='Directory containing input files')
        parser.add_argument('--output_dir', required=True, help='Directory for pipeline output')
        parser.add_argument('--min_depth', type=int, default=50, help='Minimum depth for consensus calling (default: 50)')
        parser.add_argument('--min_quality', type=int, default=30, help='Minimum quality for consensus calling (default: 30)')
        parser.add_argument('--majority_threshold', type=float, default=0.7, help='Majority rule threshold (default: 0.7)')
        args = parser.parse_args()
    
    # Convert input and output directories to Path objects
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    consensus_dir = output_dir / 'consensus'
    
    # Set up logging
    setup_logging(output_dir)
    
    # Check dependencies
    check_dependencies()
    
    # Find samples to process
    samples = [d.name for d in consensus_dir.iterdir() if d.is_dir()]
    if not samples:
        logger.error("No samples found in consensus directory")
        sys.exit(1)
    
    logger.info(f"\nFound {len(samples)} samples to process:")
    for sample in samples:
        logger.info(f"- {sample}")
    
    # Process each sample
    for sample in samples:
        sample_dir = consensus_dir / sample
        process_sample(sample_dir, sample, output_dir, args.min_depth, args.min_quality, args.majority_threshold)
    
    logger.info("\nConsensus generation complete!")

if __name__ == '__main__':
    main() 
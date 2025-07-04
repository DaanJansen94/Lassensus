# Lassensus
A tool for Lassa virus consensus sequence generation from long-read sequencing data. Given the extreme sequence divergence of Lassa viruses, proper consensus generation requires careful reference selection, which this tool automates by identifying appropriate GenBank references.

To do this, all near-complete Lassa virus genomes available in GenBank are downloaded. Sample reads are then mapped to each reference individually, and the average identity across all mapped reads is calculated. The reference with the highest overall read identity is selected as the closest match and used to guide consensus sequence generation.

## Installation

1. First, create and activate a dedicated conda environment with all required tools:
```bash
# Create conda environment and install all dependencies in one line
conda create -n lassensus -c bioconda python=3.11 minimap2 samtools ivar lassaseq seqtk medaka
conda activate lassensus
```

2. Clone and install the Lassensus package (this will install Python dependencies):

```bash
# Clone the repository
git clone https://github.com/DaanJansen94/lassensus.git
cd lassensus

# Install the package and Python dependencies
pip install .
```

## Usage

```bash
conda activate lassensus
lassensus --input_dir /path/to/input --output_dir /path/to/output [options]
```

### Required Arguments

- `--input_dir`: Directory containing input FASTQ files
- `--output_dir`: Directory where results will be saved

### Optional Arguments

- `--min_depth`: Minimum depth for consensus calling (default: 50)
  - This is the minimum number of reads that must cover a position to call a consensus base
  - Higher values will result in more stringent consensus calling
  - Lower values may allow calling consensus in regions with lower coverage

- `--min_quality`: Minimum quality score for consensus calling (default: 30)
  - This is the minimum quality score required for a base to be considered in consensus calling
  - Higher values will result in more stringent consensus calling
  - Lower values may allow calling consensus with lower quality bases

- `--majority_threshold`: Majority rule threshold (default: 0.7)
  - This is the minimum fraction of reads that must support a base to call it in the consensus
  - Value must be between 0 and 1
  - Higher values (e.g., 0.9) will require stronger support for variant calls
  - Lower values (e.g., 0.5) will allow calling variants with weaker support

### Example

```bash
# Basic usage with default parameters
lassensus --input_dir /path/to/input --output_dir /path/to/output

# Custom parameters for more stringent consensus calling
lassensus --input_dir /path/to/input --output_dir /path/to/output \
    --min_depth 100 \
    --min_quality 40 \
    --majority_threshold 0.9

# Custom parameters for more lenient consensus calling
lassensus --input_dir /path/to/input --output_dir /path/to/output \
    --min_depth 20 \
    --min_quality 20 \
    --majority_threshold 0.5
```

## Output

The tool generates the following outputs for each sample:
- `{sample_name}_L_consensus_polished.fasta`: Polished consensus sequence for the L segment
- `{sample_name}_S_consensus_polished.fasta`: Polished consensus sequence for the S segment

Additionally, the tool creates an `AllConsensus` directory containing:
- `L_segment/all_L_consensus.fasta`: Multi-fasta file containing all L segment consensus sequences
- `S_segment/all_S_consensus.fasta`: Multi-fasta file containing all S segment consensus sequences

## Dependencies

The following tools are required and will be installed in the conda environment:
- minimap2 (for read mapping)
- samtools (required by ivar)
- ivar (for consensus generation)
- lassaseq (for reference selection)
- seqtk (for read rarefaction)
- medaka (for consensus polishing)

Python dependencies (installed automatically with pip):
- biopython
- pandas
- requests

## Features

- Automatic reference selection
- Consensus generation with ivar
- Consensus polishing with medaka
- Multi-fasta generation for all consensus sequences
- Detailed mapping statistics
- Comprehensive output including JSON and human-readable summaries

## Citation

If you use Lassensus in your research, please cite:

```
Jansen, D., Laumen, J., Siebenmann, E., & Vercauteren, K. (2025). Lassenssus: A Command-Line Tool for Lassa virus consensus sequence generation from long-read sequencing data (Version v0.0.1). Zenodo. https://doi.org/10.5281/zenodo.15209207
```

## License

This project is licensed under the GNU General Public License v3.0 (GPL-3.0) - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

If you encounter any problems or have questions, please open an issue on GitHub.

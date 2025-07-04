#!/usr/bin/env python3

import os
import sys
import argparse
from pathlib import Path

# Get the absolute path to the tool's root directory
TOOL_ROOT = Path(__file__).parent.parent.absolute()

# Add the package directory to the Python path
sys.path.insert(0, str(TOOL_ROOT))

from lassensus.core.reference_selection import main as reference_selection_main
from lassensus.core.consensus_generation import main as consensus_generation_main

def main():
    """Main entry point for the Lassensus tool."""
    parser = argparse.ArgumentParser(description='Lassensus - Lassa virus consensus sequence builder')
    
    # Add main arguments that are common to all commands
    parser.add_argument('-i', '--input_dir', required=True, help='Directory containing input FASTQ files')
    parser.add_argument('-o', '--output_dir', required=True, help='Directory for pipeline output')
    parser.add_argument('--min_identity', type=float, default=90.0, help='Minimum identity threshold for reference selection (default: 90.0)')
    parser.add_argument('--genome', type=int, default=2, help='Genome completeness filter (1=Complete, 2=Partial, 3=None)')
    parser.add_argument('--completeness', type=int, default=90, help='Minimum sequence completeness (1-100 percent)')
    parser.add_argument('--host', type=int, default=4, help='Host filter (1=Human, 2=Rodent, 3=Both, 4=None)')
    parser.add_argument('--metadata', type=int, default=4, help='Metadata filter (1=Location, 2=Date, 3=Both, 4=None)')
    parser.add_argument('--min_depth', type=int, default=50, help='Minimum depth for consensus calling (default: 50)')
    parser.add_argument('--min_quality', type=int, default=30, help='Minimum quality score for consensus calling (default: 30)')
    parser.add_argument("--max_reads", type=int, default=1000000, help="Maximum number of reads to use for consensus generation (default: 1,000,000)")
    parser.add_argument('--majority_threshold', type=float, default=0.7, help='Majority rule threshold (default: 0.7)')
    
    # Optional subcommand for future expansion
    subparsers = parser.add_subparsers(dest='command', help='Pipeline stage to run (default: full pipeline)')
    
    # Reference selection subcommand
    ref_parser = subparsers.add_parser('reference-selection', help='Select reference sequences only')
    ref_parser.add_argument('-i', '--input_dir', required=True, help='Directory containing input FASTQ files')
    ref_parser.add_argument('-o', '--output_dir', required=True, help='Directory for pipeline output')
    ref_parser.add_argument('--min_identity', type=float, default=90.0, help='Minimum identity threshold for reference selection (default: 90.0)')
    ref_parser.add_argument('--genome', type=int, default=2, help='Genome completeness filter (1=Complete, 2=Partial, 3=None)')
    ref_parser.add_argument('--completeness', type=int, default=90, help='Minimum sequence completeness (1-100 percent)')
    ref_parser.add_argument('--host', type=int, default=4, help='Host filter (1=Human, 2=Rodent, 3=Both, 4=None)')
    ref_parser.add_argument('--metadata', type=int, default=4, help='Metadata filter (1=Location, 2=Date, 3=Both, 4=None)')
    
    # Consensus generation subcommand
    consensus_parser = subparsers.add_parser('consensus', help='Generate consensus sequences only')
    consensus_parser.add_argument('-i', '--input_dir', required=True, help='Directory containing input FASTQ files')
    consensus_parser.add_argument('-o', '--output_dir', required=True, help='Directory for pipeline output')
    consensus_parser.add_argument('--min_depth', type=int, default=50, help='Minimum depth for consensus calling (default: 50)')
    consensus_parser.add_argument('--min_quality', type=int, default=30, help='Minimum quality score for consensus calling (default: 30)')
    consensus_parser.add_argument('--majority_threshold', type=float, default=0.7, help='Majority rule threshold (default: 0.7)')
    consensus_parser.add_argument("--max_reads", type=int, default=1000000, help="Maximum number of reads to use for consensus generation (default: 1,000,000)")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Default to running full pipeline if no command is provided
    if not args.command:
        # Check if required arguments are provided when no subcommand is used
        if not args.input_dir or not args.output_dir:
            parser.error("the following arguments are required: --input_dir/-i, --output_dir/-o")
        
        # Run reference selection first
        reference_selection_main(args)
        # Then run consensus generation
        consensus_generation_main(args)
    else:
        # Execute the specific command
        if args.command == 'reference-selection':
            reference_selection_main(args)
        elif args.command == 'consensus':
            consensus_generation_main(args)

if __name__ == "__main__":
    main() 
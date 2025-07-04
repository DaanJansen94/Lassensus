# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Support for both `.fastq` and `.fastq.gz` input files
- `--max_reads` parameter for consensus generation (default: 1,000,000)
- Smart rarefaction: only rarefy if input exceeds max_reads threshold
- Better input validation and error handling for file types
- Environment.yml for reproducible conda installations
- Requirements.txt for pip-only installations

### Fixed
- **CRITICAL**: Read counting function now properly handles both compressed and uncompressed FASTQ files
- NumPy 2.0 compatibility issue with medaka (constrained to numpy<2.0)
- Missing dependencies: ont-mappy, ont-parasail
- h5py version compatibility (pinned to ~3.10.0)
- File processing logic in both reference selection and consensus generation

### Changed
- Updated installation instructions to avoid dependency conflicts
- Improved error messages for file type detection
- Enhanced documentation with troubleshooting section

## [0.0.2] - Previous Release

### Added
- Initial pipeline implementation
- Reference selection functionality
- Consensus generation with medaka polishing
- Basic FASTQ file processing 
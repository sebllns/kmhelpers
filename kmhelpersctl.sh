#!/bin/bash

# kmhelpers - Bash utility functions for k-mer index management
# Provides convenience functions for registering and managing indices

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

CTL_VERSION='0.3.1'
KMHELPERS_VERSION='dev/v0.5.5'
KMINDEX_VERSION='v0.6.0'

# Initialize global variables - KMHELPERS_PATH may be set from environment
# If not set in environment, it will be initialized to default in init_kmhelpers_path()
: "${KMHELPERS_PATH:=}"
VENV_DIR=""
INSTALL_PATH=""
SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

# ============================================================================
# INITIALIZATION & CONFIGURATION
# ============================================================================

# Initialize paths and parse command-line arguments
function init_kmhelpers_path()
{
    # Parse -w/--workdir from command line
    local workdir_override=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -w|--workdir)
                workdir_override="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done

    # Set KMHELPERS_PATH from environment variable or use default
    if [[ -z "${KMHELPERS_PATH}" ]]; then
        KMHELPERS_PATH="${HOME}/.kmhelpers"
    fi

    # Override with command-line argument if provided
    if [[ -n "$workdir_override" ]]; then
        KMHELPERS_PATH="$workdir_override"
    fi

    # Set derived paths
    VENV_DIR="$KMHELPERS_PATH/kmhelpers_env"
    INSTALL_PATH="$KMHELPERS_PATH/kmhelpersctl"
}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*" >&2
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

# ============================================================================
# REGISTRY FUNCTIONS
# ============================================================================

# Register a single index in the registry
# Usage: register_index <registry_folder> <index_name> <index_path>
function register_index()
{
    local registry_folder="$1"
    local index_name="$2"
    local index_path="$3"

    # Validate arguments
    if [[ -z "$registry_folder" || -z "$index_name" || -z "$index_path" ]]; then
        log_error "register_index: Missing required arguments"
        echo "Usage: register_index <registry_folder> <index_name> <index_path>"
        return 1
    fi

    # Check if index path exists
    if [[ ! -d "$index_path" ]]; then
        log_error "Index path does not exist: $index_path"
        return 1
    fi

    # Check if index already exists in registry
    if [[ -d "${registry_folder}/${index_name}" ]]; then
        log_warn "Index '${index_name}' already exists in registry, skipping"
        return 0
    fi

    log_info "Registering index: ${index_name}"
    log_info "  Path: ${index_path}"
    log_info "  Registry: ${registry_folder}"

    # Call kmindex register
    if kmindex register -i "${registry_folder}" -n "${index_name}" -p "${index_path}"; then
        log_info "Successfully registered: ${index_name}"
        return 0
    else
        log_error "Failed to register index: ${index_name}"
        return 1
    fi
}

# Register all indices from a directory
# Usage: register_all_indices <registry_folder> <indices_parent_directory>
function register_all_indices()
{
    local registry_folder="$1"
    local indices_directory="$2"

    # Validate arguments
    if [[ -z "$registry_folder" || -z "$indices_directory" ]]; then
        log_error "register_all_indices: Missing required arguments"
        echo "Usage: register_all_indices <registry_folder> <indices_parent_directory>"
        return 1
    fi

    # Check if registry directory exists
    if [[ ! -d "$registry_folder" ]]; then
        log_error "Registry folder does not exist: $registry_folder"
        return 1
    fi

    # Check if indices directory exists
    if [[ ! -d "$indices_directory" ]]; then
        log_error "Indices directory does not exist: $indices_directory"
        return 1
    fi

    log_info "Registering all indices from: ${indices_directory}"

    local success_count=0
    local skip_count=0
    local fail_count=0

    # Iterate through subdirectories
    for dir in "${indices_directory}"/*; do
        if [[ -d "$dir" ]]; then
            local index_path="$dir"
            local index_name="${index_path##*/}"  # Get directory name

            if register_index "${registry_folder}" "${index_name}" "${index_path}"; then
                ((success_count++))
            else
                if [[ -d "${registry_folder}/${index_name}" ]]; then
                    ((skip_count++))
                else
                    ((fail_count++))
                fi
            fi
        fi
    done

    # Summary
    echo ""
    log_info "Registration complete:"
    log_info "  Successful: ${success_count}"
    log_info "  Skipped (already registered): ${skip_count}"
    log_info "  Failed: ${fail_count}"

    return 0
}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

# List all registered indices in a registry
# Usage: list_indices <registry_folder>
function list_indices()
{
    local registry_folder="$1"

    if [[ -z "$registry_folder" ]]; then
        log_error "list_indices: Missing registry folder argument"
        return 1
    fi

    if [[ ! -d "$registry_folder" ]]; then
        log_error "Registry folder does not exist: $registry_folder"
        return 1
    fi

    local count=0
    log_info "Registered indices in ${registry_folder}:"

    for dir in "${registry_folder}"/*; do
        if [[ -d "$dir" ]]; then
            local index_name="${dir##*/}"
            echo "  - ${index_name}"
            ((count++))
        fi
    done

    if [[ $count -eq 0 ]]; then
        log_warn "No indices found in registry"
    else
        log_info "Total indices: ${count}"
    fi
}

# Check if kmindex binary is available
# Usage: check_kmindex
function check_kmindex()
{
    if command -v kmindex &> /dev/null; then
        log_info "kmindex is installed: $(kmindex --version 2>&1 | head -1)"
        log_info "kmindex path: $(which kmindex 2>&1 | head -1)"
        return 0
    else
        log_error "kmindex binary not found in PATH"
        log_info "Install kmindex or add it to PATH"
        return 1
    fi
}

# ============================================================================
# ANALYSIS FUNCTIONS
# ============================================================================

# Get the size of a single index
# Usage: get_index_size <index_path>
function get_index_size()
{
    local index_path="$1"

    if [[ -z "$index_path" ]]; then
        log_error "get_index_size: Missing index path argument"
        return 1
    fi

    if [[ ! -d "$index_path" ]]; then
        log_error "Index path does not exist: $index_path"
        return 1
    fi

    local index_name="${index_path##*/}"
    local total_size=0
    local partition_count=0

    log_info "Calculating size for index: ${index_name}"
    echo ""

    # Get size of partitions
    if [[ -d "${index_path}/matrices" ]]; then
        local partition_dir="${index_path}/matrices"
        for partition_file in "${partition_dir}"/*; do
            if [[ -f "$partition_file" ]]; then
                local file_size=$(stat -f%z "$partition_file" 2>/dev/null || stat -c%s "$partition_file" 2>/dev/null || echo "0")
                local file_name=$(basename "$partition_file")
                local size_mb=$((file_size / 1024 / 1024))
                echo "  ${file_name}: ${size_mb} MB"
                ((total_size += file_size))
                ((partition_count++))
            fi
        done
    fi

    # Get size of other files
    local metadata_size=0
    for file in "${index_path}"/*.json "${index_path}"/*.yaml "${index_path}"/*.bin; do
        if [[ -f "$file" ]]; then
            local file_size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo "0")
            local file_name=$(basename "$file")
            echo "  ${file_name}: $((file_size / 1024)) KB"
            ((metadata_size += file_size))
        fi
    done 2>/dev/null

    # Calculate total
    local total_mb=$((total_size / 1024 / 1024))
    local metadata_kb=$((metadata_size / 1024))

    echo ""
    log_info "Size Summary for ${index_name}:"
    log_info "  Partitions: ${partition_count} files"
    log_info "  Partition data: ${total_mb} MB"
    log_info "  Metadata: ${metadata_kb} KB"
    log_info "  Total: $((total_mb)) MB"

    return 0
}

# Get statistics for all indices in a registry
# Usage: get_registry_stats <registry_folder>
function get_registry_stats()
{
    local registry_folder="$1"

    if [[ -z "$registry_folder" ]]; then
        log_error "get_registry_stats: Missing registry folder argument"
        return 1
    fi

    if [[ ! -d "$registry_folder" ]]; then
        log_error "Registry folder does not exist: $registry_folder"
        return 1
    fi

    local total_indices=0
    local total_samples=0
    local total_size=0
    local total_partitions=0

    log_info "Gathering registry statistics for: ${registry_folder}"
    echo ""

    # Iterate through all indices
    for index_dir in "${registry_folder}"/*; do
        if [[ -d "$index_dir" ]]; then
            local index_name="${index_dir##*/}"
            ((total_indices++))

            # Count samples (directories in the index)
            local sample_count=0
            if [[ -d "${index_dir}/matrices" ]]; then
                # Count files in matrices directory as proxy for partitions
                local partition_count=$(ls -1 "${index_dir}/matrices" 2>/dev/null | wc -l || echo "0")
                ((total_partitions += partition_count))
            fi

            # Calculate size
            local index_size=0
            if [[ -d "${index_dir}/matrices" ]]; then
                for file in "${index_dir}/matrices"/*; do
                    if [[ -f "$file" ]]; then
                        local file_size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo "0")
                        ((index_size += file_size))
                    fi
                done
            fi

            local index_size_mb=$((index_size / 1024 / 1024))
            ((total_size += index_size))

            printf "  %-30s %10d MB\n" "${index_name}:" "${index_size_mb}"
        fi
    done

    if [[ $total_indices -eq 0 ]]; then
        log_warn "No indices found in registry"
        return 0
    fi

    # Print summary
    echo ""
    local total_size_gb=$((total_size / 1024 / 1024 / 1024))
    local avg_size_mb=$((total_size / total_indices / 1024 / 1024))

    log_info "Registry Statistics:"
    log_info "  Total indices: ${total_indices}"
    log_info "  Total partitions: ${total_partitions}"
    log_info "  Total disk usage: ${total_size_gb} GB (${total_size} bytes)"
    log_info "  Average index size: ${avg_size_mb} MB"

    return 0
}

# Search for indices matching a pattern
# Usage: search_indices <registry_folder> <pattern> [--size-filter SIZE_MB]
function search_indices()
{
    local registry_folder="$1"
    local search_pattern="$2"
    local size_filter=""

    # Parse optional arguments
    for arg in "$@"; do
        if [[ "$arg" == "--size-filter" ]]; then
            size_filter="${!((${#@}))}"
        fi
    done

    if [[ -z "$registry_folder" ]]; then
        log_error "search_indices: Missing registry folder argument"
        return 1
    fi

    if [[ -z "$search_pattern" ]]; then
        log_error "search_indices: Missing search pattern argument"
        echo "Usage: search_indices <registry_folder> <pattern> [--size-filter SIZE_MB]"
        return 1
    fi

    if [[ ! -d "$registry_folder" ]]; then
        log_error "Registry folder does not exist: $registry_folder"
        return 1
    fi

    local match_count=0

    log_info "Searching for indices matching pattern: '${search_pattern}'"
    if [[ -n "$size_filter" ]]; then
        log_info "Size filter: >= ${size_filter} MB"
    fi
    echo ""

    # Search through indices
    for index_dir in "${registry_folder}"/*; do
        if [[ -d "$index_dir" ]]; then
            local index_name="${index_dir##*/}"

            # Check if name matches pattern
            if [[ "$index_name" == *"$search_pattern"* ]]; then
                # Calculate size
                local index_size=0
                if [[ -d "${index_dir}/matrices" ]]; then
                    for file in "${index_dir}/matrices"/*; do
                        if [[ -f "$file" ]]; then
                            local file_size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo "0")
                            ((index_size += file_size))
                        fi
                    done
                fi

                local index_size_mb=$((index_size / 1024 / 1024))

                # Apply size filter if specified
                if [[ -n "$size_filter" ]]; then
                    if [[ $index_size_mb -lt $size_filter ]]; then
                        continue
                    fi
                fi

                printf "  %-40s %10d MB\n" "${index_name}" "${index_size_mb}"
                ((match_count++))
            fi
        fi
    done

    echo ""
    if [[ $match_count -eq 0 ]]; then
        log_warn "No indices found matching pattern: '${search_pattern}'"
        return 1
    else
        log_info "Found ${match_count} matching indices"
        return 0
    fi
}

# ============================================================================
# KMINDEX INSTALLATION
# ============================================================================

# Install kmindex using conda
function install_kmindex_conda()
{
    local env_path="${1:-$KMHELPERS_PATH/kmindex_env}"

    log_info "Installing kmindex via conda in environment: ${env_path}"

    if ! command -v conda &> /dev/null; then
        log_error "conda not found. Install Miniconda or Anaconda first."
        return 1
    fi

    # Create environment if it doesn't exist
    if [[ ! -d "$env_path" ]]; then
        log_info "Creating conda environment at: ${env_path}"
        if ! conda create -y -p "${env_path}"; then
            log_error "Failed to create conda environment"
            return 1
        fi
    else
        log_info "Using existing conda environment: ${env_path}"
    fi

    # Install kmindex from bioconda
    log_info "Installing kmindex from bioconda..."
    if conda run -p "${env_path}" conda install -y -c bioconda kmindex; then
        log_info "Successfully installed kmindex in ${env_path}"
        log_info "To use kmindex, activate the environment:"
        echo "  conda activate -p ${env_path}"
        return 0
    else
        log_error "Failed to install kmindex"
        return 1
    fi
}

# Build and install kmindex from source
function install_kmindex_source()
{
    local install_prefix="${1:-.}"
    local kmindex_dir="${2:-.}"
    local build_type="${3:-Release}"
    local max_kmer="${4:-256}"
    local threads="${5:-8}"
    local tests="${6:-0}"
    local portable="${7:-OFF}"

    log_info "Building kmindex from source"
    log_info "  Source: ${kmindex_dir}"
    log_info "  Install prefix: ${install_prefix}"
    log_info "  Build type: ${build_type}"
    log_info "  Max k-mer size: ${max_kmer}"
    log_info "  Threads: ${threads}"

    # Check if kmindex directory exists
    if [[ ! -d "${kmindex_dir}" ]]; then
        log_error "kmindex directory not found: ${kmindex_dir}"
        return 1
    fi

    # Check if kmindex CMakeLists.txt exists
    if [[ ! -f "${kmindex_dir}/CMakeLists.txt" ]]; then
        log_error "CMakeLists.txt not found in ${kmindex_dir}"
        return 1
    fi

    # Validate build type
    if [[ "${build_type}" != "Release" && "${build_type}" != "Debug" ]]; then
        log_error "Invalid build type. Use 'Release' or 'Debug'"
        return 1
    fi

    # Create build directory
    local build_dir="${kmindex_dir}/kmbuild"
    mkdir -p "${build_dir}"
    cd "${build_dir}" || return 1

    log_info "Running cmake..."
    if ! cmake .. \
        -DCMAKE_BUILD_TYPE="${build_type}" \
        -DWITH_TESTS=$([ "${tests}" -eq 0 ] && echo "OFF" || echo "ON") \
        -DWITH_SERVER="OFF" \
        -DCMAKE_CXX_STANDARD=17 \
        -DPORTABLE_BUILD="${portable}" \
        -DCMAKE_INSTALL_PREFIX="$(realpath "${install_prefix}")" \
        -DMAX_KMER_SIZE="${max_kmer}"; then
        log_error "cmake configuration failed"
        return 1
    fi

    log_info "Building with ${threads} threads..."
    if ! make -j"${threads}"; then
        log_error "Build failed"
        return 1
    fi

    # Run tests if requested
    if [[ "${tests}" -eq 2 ]]; then
        log_info "Running tests..."
        if ! ctest --verbose; then
            log_error "Tests failed"
            return 1
        fi
    fi

    log_info "Installing kmindex..."
    if ! make install; then
        log_error "Installation failed"
        return 1
    fi

    log_info "Successfully installed kmindex to: $(realpath "${install_prefix}")"
    return 0
}

# Clone kmindex repository
function clone_kmindex_repo()
{
    local target_dir="${1:-.}"

    log_info "Cloning kmindex from GitHub..."

    if ! command -v git &> /dev/null; then
        log_error "git not found. Please install git."
        return 1
    fi

    # Clone with specific version/tag if available
    if [[ -n "$KMINDEX_VERSION" ]] && [[ "$KMINDEX_VERSION" != "latest" ]]; then
        log_info "Cloning kmindex version: ${KMINDEX_VERSION}"
        if git clone --recursive --branch "${KMINDEX_VERSION}" https://github.com/tlemane/kmindex "${target_dir}"; then
            log_info "Successfully cloned kmindex ${KMINDEX_VERSION} to: ${target_dir}"
            return 0
        else
            log_warn "Failed to clone specific version ${KMINDEX_VERSION}, trying latest..."
            # Fallback to latest
        fi
    fi

    # Clone latest if no version specified or fallback
    if git clone --recursive https://github.com/tlemane/kmindex "${target_dir}"; then
        log_info "Successfully cloned kmindex to: ${target_dir}"
        return 0
    else
        log_error "Failed to clone kmindex repository"
        return 1
    fi
}

# Main kmindex installation function
function install_kmindex()
{
    local method="${1:-conda}"
    local env_or_path="${2:-}"
    shift 2

    case "${method}" in
        conda)
            install_kmindex_conda "${env_or_path}"
            ;;
        source)
            local kmindex_src="${env_or_path}"
            if [[ -z "${kmindex_src}" ]]; then
                log_error "install_kmindex source: missing source directory argument"
                return 1
            fi
            install_kmindex_source "$@"
            ;;
        clone-source)
            local target_dir="${env_or_path:-.}"
            if ! clone_kmindex_repo "${target_dir}"; then
                return 1
            fi
            # After cloning, ask if user wants to build
            log_info "Repository cloned. To build, run either:"
            echo "  kmhelpersctl install-kmindex source ${target_dir} Release 256 8 0"
            echo ""
            echo "Or:"
            echo "  cd ${target_dir} && kmhelpers install_kmindex source . Release 256 8 0"
            return 0
            ;;
        conda-build)
            # Default: Install from sources in conda environment
            log_info "Installing kmindex from sources using conda environment"
            log_info ""

            # Check if conda is available
            if ! command -v conda &> /dev/null; then
                log_error "conda not found. Please install Miniconda or Anaconda first."
                log_error "Visit: https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html"
                return 1
            fi

            # Create conda environment
            local conda_env_path="${KMHELPERS_PATH}/kmindex_env"
            log_info "Creating conda environment at: ${conda_env_path}"

            if [[ ! -d "$conda_env_path" ]]; then
                if ! conda create -y -p "${conda_env_path}" python=3.11; then
                    log_error "Failed to create conda environment"
                    return 1
                fi
            else
                log_info "Using existing conda environment: ${conda_env_path}"
            fi

            # Install required tools in conda environment
            log_info "Installing build tools in conda environment..."
            log_info "  - cmake==3.27"
            log_info "  - gcc==12.2.0 (with g++)"
            log_info "  - git==2.48"
            log_info "  - zlib (for external dependencies)"

            if ! conda run -p "${conda_env_path}" conda install -y -c conda-forge \
                "cmake=3.27" \
                "gcc=12.2.0" \
                "gxx=12.2.0" \
                "git=2.48" \
                "zlib"; then
                log_error "Failed to install build tools in conda environment"
                return 1
            fi

            log_info "✓ Build tools installed successfully"

            # Clone kmindex if target directory not provided
            local kmindex_src="${env_or_path:-.}"
            if [[ "$kmindex_src" == "." ]]; then
                kmindex_src="${KMHELPERS_PATH}/kmindex"
            fi

            if [[ ! -d "$kmindex_src" ]]; then
                log_info "Cloning kmindex to: ${kmindex_src}"
                if ! clone_kmindex_repo "${kmindex_src}"; then
                    log_error "Failed to clone kmindex"
                    return 1
                fi
            else
                log_info "Using existing kmindex source at: ${kmindex_src}"
            fi

            # Build and install kmindex using conda environment
            log_info "Building kmindex from source..."
            if ! conda run -p "${conda_env_path}" bash -c "cd ${kmindex_src} && \
                mkdir -p kmbuild && \
                cd kmbuild && \
                cmake .. -DCMAKE_BUILD_TYPE=Release -DWITH_TESTS=OFF -DWITH_SERVER=OFF \
                    -DCMAKE_CXX_STANDARD=17 -DPORTABLE_BUILD=OFF \
                    -DCMAKE_INSTALL_PREFIX='${conda_env_path}' -DMAX_KMER_SIZE=256 && \
                make -j8 && \
                make install"; then
                log_error "Failed to build kmindex"
                return 1
            fi

            log_info "============================================================="
            log_info "✓ kmindex installation completed successfully!"
            log_info "============================================================="
            log_info ""
            log_info "To use kmindex, activate the conda environment:"
            echo "  conda activate -p ${conda_env_path}"
            log_info ""
            log_info "Then kmindex will be available in your PATH:"
            echo "  kmindex --version"
            log_info ""
            return 0
            ;;
        *)
            log_error "Unknown command: ${command}"
            echo "Run 'kmhelpersctl help' for usage information"
            return 1
            ;;
    esac
}

# Print install_kmindex help
function install_kmindex_help()
{
    cat <<EOF
kmindex Installation Options

USAGE:
    kmhelpersctl install-kmindex [METHOD] [TARGET_DIR]

METHODS:
    conda [ENV_PATH] (default) 
        Install kmindex from bioconda
        ENV_PATH: conda environment path (default: ${KMHELPERS_PATH}/kmindex_env)

        Example:
          kmhelpersctl install-kmindex conda
          kmhelpersctl install-kmindex conda /custom/path/kmindex_env

    source <SOURCE_DIR> [BUILD_TYPE] [MAX_KMER] [THREADS] [TESTS] [PORTABLE]
        Build and install kmindex from source
        SOURCE_DIR: path to kmindex repository
        BUILD_TYPE: Release or Debug (default: Release)
        MAX_KMER: maximum k-mer size (default: 256, must be multiple of 32)
        THREADS: build threads (default: 8)
        TESTS: 0=no tests, 1=compile tests, 2=run tests (default: 0)
        PORTABLE: ON or OFF for portable x86-64 build (default: OFF)

        Example:
          kmhelpersctl install-kmindex source /path/to/kmindex
          kmhelpersctl install-kmindex source /path/to/kmindex Release 256 8 2

    clone-source [TARGET_DIR]
        Clone kmindex repository from GitHub (without building)
        TARGET_DIR: where to clone (default: ${KMHELPERS_PATH}/kmindex)

    conda-build
        Automatic installation from sources using conda environment
        - Creates conda environment at ${KMHELPERS_PATH}/kmindex_env
        - Installs build tools via conda-forge:
          * cmake==3.27
          * gcc==12.2.0 (with g++)
          * git==2.48
          * zlib (for external dependencies)
        - Clones kmindex (or uses existing source)
        - Builds and installs kmindex into conda environment

        Example:
          kmhelpersctl install-kmindex conda-build

EXAMPLES:

    # Quick install (recommended - automatic)
    kmhelpersctl install-kmindex

    # Install from conda (default path: ${KMHELPERS_PATH}/kmindex_env)
    kmhelpersctl install-kmindex conda

    # Install from conda (custom path)
    kmhelpersctl install-kmindex conda /opt/kmindex

    # Clone only (then build separately)
    kmhelpersctl install-kmindex clone-source ./kmindex
    kmhelpersctl install-kmindex source ./kmindex Release 256 8 2

    # Build existing kmindex source directory
    kmhelpersctl install-kmindex source ~/src/kmindex Release

For more information, visit: https://github.com/tlemane/kmindex
EOF
}

install_kmindex_completion() {
    local comp_dir="${HOME}/.zsh/completions"
    local comp_file="${comp_dir}/_kmindex"

    mkdir -p "$comp_dir"

    cat > "$comp_file" << 'EOF'
#compdef kmindex

_kmindex_build() {
    _arguments \
        '-i[Global index path]:path:_files -/' \
        '--index[Global index path]:path:_files -/' \
        '-f[kmtricks input file]:file:_files' \
        '--fof[kmtricks input file]:file:_files' \
        '-d[kmtricks runtime directory]:path:_files -/' \
        '--run-dir[kmtricks runtime directory]:path:_files -/' \
        '-r[Index name]:name:' \
        '--register-as[Index name]:name:' \
        '--from[Use parameters from a pre-registered index]:name:' \
        '--km-path[Path to kmtricks binary]:file:_files' \
        '-k[Size of a k-mer (8-255)]:int:' \
        '--kmer-size[Size of a k-mer (8-255)]:int:' \
        '-m[Size of minimizers (4-15)]:int:' \
        '--minim-size[Size of minimizers (4-15)]:int:' \
        '--hard-min[Min abundance to keep a k-mer]:int:' \
        '--nb-partitions[Number of partitions (0=auto)]:int:' \
        '--cpr[Compress intermediate files]' \
        '--bloom-size[Bloom filter size]:int:' \
        '--nb-cell[Number of cells in counting Bloom filter]:int:' \
        '--bitw[Number of bits per cell]:int:' \
        '-t[Number of threads]:int:' \
        '--threads[Number of threads]:int:' \
        '-v[Verbosity level]:level:(debug info warning error)' \
        '--verbose[Verbosity level]:level:(debug info warning error)' \
        '-h[Show help]' \
        '--help[Show help]' \
        '--version[Show version]'
}

_kmindex_register() {
    _arguments \
        '-i[Global index path]:path:_files -/' \
        '--global-index[Global index path]:path:_files -/' \
        '-n[Index name]:name:' \
        '--name[Index name]:name:' \
        '-p[Index path (a kmtricks run)]:path:_files -/' \
        '--index-path[Index path (a kmtricks run)]:path:_files -/' \
        '-f[Tab-separated file with index_name<tab>index_path]:file:_files' \
        '--from-file[Tab-separated file with index_name<tab>index_path]:file:_files' \
        '-v[Verbosity level]:level:(debug info warning error)' \
        '--verbose[Verbosity level]:level:(debug info warning error)' \
        '-h[Show help]' \
        '--help[Show help]' \
        '--version[Show version]'
}

_kmindex_query() {
    _arguments \
        '-i[Global index path]:path:_files -/' \
        '--index[Global index path]:path:_files -/' \
        '-q[Input fasta/q file]:file:_files' \
        '--fastx[Input fasta/q file]:file:_files' \
        '-n[Sub-indexes to query, comma separated]:names:' \
        '--names[Sub-indexes to query, comma separated]:names:' \
        '-z[Z-value for findere algorithm]:int:' \
        '--zvalue[Z-value for findere algorithm]:int:' \
        '-r[Shared k-mers threshold (0.0-1.0)]:float:' \
        '--threshold[Shared k-mers threshold (0.0-1.0)]:float:' \
        '-o[Output directory]:path:_files -/' \
        '--output[Output directory]:path:_files -/' \
        '-s[Query identifier for single query]:id:' \
        '--single-query[Query identifier for single query]:id:' \
        '-f[Output format]:format:(json matrix json_vec jsonl jsonl_vec)' \
        '--format[Output format]:format:(json matrix json_vec jsonl jsonl_vec)' \
        '-b[Size of query batches]:int:' \
        '--batch-size[Size of query batches]:int:' \
        '-a[Aggregate results from batches]' \
        '--aggregate[Aggregate results from batches]' \
        '--fast[Keep more pages in cache]' \
        '-t[Number of threads]:int:' \
        '--threads[Number of threads]:int:' \
        '-v[Verbosity level]:level:(debug info warning error)' \
        '--verbose[Verbosity level]:level:(debug info warning error)' \
        '-h[Show help]' \
        '--help[Show help]' \
        '--version[Show version]'
}

_kmindex_merge() {
    _arguments \
        '-i[Global index path]:path:_files -/' \
        '--index[Global index path]:path:_files -/' \
        '-n[Name of the new index]:name:' \
        '--new-name[Name of the new index]:name:' \
        '-p[Output path]:path:_files -/' \
        '--new-path[Output path]:path:_files -/' \
        '-m[Sub-indexes to merge, comma separated]:names:' \
        '--to-merge[Sub-indexes to merge, comma separated]:names:' \
        '-d[Delete old sub-index files]' \
        '--delete-old[Delete old sub-index files]' \
        '-r[Rename sample ids]:rename:' \
        '--rename[Rename sample ids]:rename:' \
        '-t[Number of threads]:int:' \
        '--threads[Number of threads]:int:' \
        '-v[Verbosity level]:level:(debug info warning error)' \
        '--verbose[Verbosity level]:level:(debug info warning error)' \
        '-h[Show help]' \
        '--help[Show help]' \
        '--version[Show version]'
}

_kmindex_index_infos() {
    _arguments \
        '-i[Global index path]:path:_files -/' \
        '--index[Global index path]:path:_files -/' \
        '-v[Verbosity level]:level:(debug info warning error)' \
        '--verbose[Verbosity level]:level:(debug info warning error)' \
        '-h[Show help]' \
        '--help[Show help]' \
        '--version[Show version]'
}

_kmindex_compress() {
    _arguments \
        '-i[Global index path]:path:_files -/' \
        '--global-index[Global index path]:path:_files -/' \
        '-n[Index name]:name:' \
        '--name[Index name]:name:' \
        '-b[Size of uncompressed blocks in MB]:int:' \
        '--block-size[Size of uncompressed blocks in MB]:int:' \
        '-s[Number of rows to sample for reordering]:int:' \
        '--sampling[Number of rows to sample for reordering]:int:' \
        '-c[Reorder columns by group of N]:int:' \
        '--column-per-block[Reorder columns by group of N]:int:' \
        '-d[Delete uncompressed index after compressing]' \
        '--delete[Delete uncompressed index after compressing]' \
        '--check[Check query results after compressing]' \
        '-r[Reorder columns before compressing]' \
        '--reorder[Reorder columns before compressing]' \
        '-t[Number of threads]:int:' \
        '--threads[Number of threads]:int:' \
        '-v[Verbosity level]:level:(debug info warning error)' \
        '--verbose[Verbosity level]:level:(debug info warning error)' \
        '-h[Show help]' \
        '--help[Show help]' \
        '--version[Show version]'
}

_kmindex_sum_index() {
    _arguments \
        '-i[Global index path]:path:_files -/' \
        '--global-index[Global index path]:path:_files -/' \
        '-n[Index name]:name:' \
        '--name[Index name]:name:' \
        '-c[False positive rate correction factor (0.0-1.0)]:float:' \
        '--fp-correction[False positive rate correction factor (0.0-1.0)]:float:' \
        '-e[Estimate the false positive rate correction factor]' \
        '--estimate-correction[Estimate the false positive rate correction factor]' \
        '-s[Number of k-mers for estimating correction]:int:' \
        '--nbk[Number of k-mers for estimating correction]:int:' \
        '-t[Number of threads]:int:' \
        '--threads[Number of threads]:int:' \
        '-v[Verbosity level]:level:(debug info warning error)' \
        '--verbose[Verbosity level]:level:(debug info warning error)' \
        '-h[Show help]' \
        '--help[Show help]' \
        '--version[Show version]'
}

_kmindex_sum_query() {
    _arguments \
        '-i[Global index path]:path:_files -/' \
        '--global-index[Global index path]:path:_files -/' \
        '-q[Input fasta/q file]:file:_files' \
        '--fastx[Input fasta/q file]:file:_files' \
        '-n[Sub-indexes to query, comma separated]:names:' \
        '--names[Sub-indexes to query, comma separated]:names:' \
        '-z[Z-value for findere algorithm]:int:' \
        '--zvalue[Z-value for findere algorithm]:int:' \
        '-o[Output directory]:path:_files -/' \
        '--output[Output directory]:path:_files -/' \
        '-t[Number of threads]:int:' \
        '--threads[Number of threads]:int:' \
        '-v[Verbosity level]:level:(debug info warning error)' \
        '--verbose[Verbosity level]:level:(debug info warning error)' \
        '-h[Show help]' \
        '--help[Show help]' \
        '--version[Show version]'
}

_kmindex() {
    local curcontext="$curcontext" state line

    _arguments -C \
        '1:command:->command' \
        '*::args:->args'

    case $state in
        command)
            local commands=(
                'build:Build index'
                'register:Register index'
                'query:Query index'
                'merge:Merge sub-indexes'
                'index-infos:Print index informations'
                'compress:Compress index'
                'sum-index:Make a lightweight summarized index'
                'sum-query:Query a summarized index'
            )
            _describe 'command' commands
            ;;
        args)
            case $line[1] in
                build)      _kmindex_build ;;
                register)   _kmindex_register ;;
                query)      _kmindex_query ;;
                merge)      _kmindex_merge ;;
                index-infos) _kmindex_index_infos ;;
                compress)   _kmindex_compress ;;
                sum-index)  _kmindex_sum_index ;;
                sum-query)  _kmindex_sum_query ;;
            esac
            ;;
    esac
}

_kmindex "$@"
EOF

    # Add fpath to zshrc if not already present
    local zshrc="${HOME}/.zshrc"
    local fpath_line='fpath=(~/.zsh/completions $fpath)'
    if ! grep -qF "$fpath_line" "$zshrc" 2>/dev/null; then
        echo "$fpath_line" >> "$zshrc"
        echo "autoload -Uz compinit && compinit" >> "$zshrc"
    fi

    echo "Installed kmindex completion to $comp_file"
    echo "Restart your shell or run: source ~/.zshrc"
}

# ============================================================================
# MAIN INTERFACE & INSTALLATION
# ============================================================================

# Print help message
function help()
{
    cat <<EOF
kmhelpersctl v${CTL_VERSION} - Bash utility functions for k-mer index management

USAGE:
    kmhelpersctl [GLOBAL_OPTIONS] [COMMAND] [OPTIONS]

GLOBAL OPTIONS:
    -w, --workdir <PATH>       Override KMHELPERS_PATH environment variable

COMMANDS:
    register <registry> <name> <path>      Register a single index
    register-all <registry> <directory>    Register all indices from a directory
    list <registry>                        List all registered indices
    search <registry> <pattern>            Search for indices by pattern
    stats <registry>                       Get registry statistics
    size <index_path>                      Get size of a single index
    check                                  Check if kmindex binary is available
    install-kmindex [METHOD] [PATH]        Install kmindex (automatic/conda/source/clone-source)
    install-kmhelpersctl                   Install kmhelpersctl to shell configuration
    install-pykmhelpers [OPTIONS]          Install kmhelpers python package
                                           Options:
                                             --inplace         Install in current Python environment
                                             -p, --path        Custom path for virtual environment (default: ${VENV_DIR})
                                             -v, --version     kmhelpers version/branch to install (default: ${KMHELPERS_VERSION})
                                             --no-alias        Skip creating activation alias
    install_kmindex_completion             Install kmindex completion in zsh
    activate-venv [OPTIONS]                Print instruction to activate kmhelpers virtual environment
                                           Options:
                                             -p, --path   Path to virtual environment (default: ${VENV_DIR})
    update-shell [OPTIONS]                 Update kmhelpersctl from GitLab
                                           Options:
                                             -v, --version Version/branch to update to (default: ${KMHELPERS_VERSION})
    help                                   Show this help message
    version                                Show version information

EXAMPLES:
    kmhelpersctl register /path/to/registry my_index /path/to/index
    kmhelpersctl stats /path/to/registry
    kmhelpersctl search /path/to/registry "pattern" --size-filter 100
    kmhelpersctl install-kmindex                        # Quick automatic installation
    kmhelpersctl install-kmindex conda                  # Install via conda (default path)
    kmhelpersctl install-kmindex conda /custom/path     # Install via conda (custom path)
    kmhelpersctl install-pykmhelpers                    # Install in ~/.kmhelpers/env
    kmhelpersctl install-pykmhelpers --inplace          # Install in current environment
    kmhelpersctl install-pykmhelpers -p /custom/path    # Install in custom venv path
    kmhelpersctl install-pykmhelpers -v main            # Install specific version/branch
    kmhelpersctl install-pykmhelpers -v main -p /path   # Install specific version with custom venv path
    kmhelpersctl install-pykmhelpers --no-alias         # Install without creating alias
    kmhelpers-activate                                  # Quick activation of venv (after install)
    kmhelpersctl activate-venv                          # Show activation command for default venv
    kmhelpersctl activate-venv -p /custom/path          # Show activation command for custom venv
    kmhelpersctl update-shell                           # Update from default version (dev/v0.5.5)
    kmhelpersctl update-shell -v main                   # Update from specific version/branch

For more information, visit: https://gitlab.inria.fr/omicfinder/kmhelpers
EOF
}


# Print version information
function version()
{
    echo "kmhelpersctl v${CTL_VERSION}"
}

# Install shell activation function
function install_shell_activation_function()
{
    local venv_path="$1"
    local no_alias="$2"

    if [[ "$no_alias" == true ]]; then
        return 0
    fi

    local func_name="kmhelpers-activate"
    local func_line="alias ${func_name}=\"source ${venv_path}/bin/activate\""

    log_info "Installing activation function: ${func_name}"

    # Install for bash
    if [[ -f "$HOME/.bashrc" ]]; then
        if ! grep -qF "${func_name}" "$HOME/.bashrc"; then
            echo "" >> "$HOME/.bashrc"
            echo "# Activate kmhelpers venv" >> "$HOME/.bashrc"
            echo "${func_line}" >> "$HOME/.bashrc"
            log_info "Added ${func_name} to ~/.bashrc"
        fi
    fi

    # Install for zsh
    if [[ -f "$HOME/.zshrc" ]]; then
        if ! grep -qF "${func_name}" "$HOME/.zshrc"; then
            echo "" >> "$HOME/.zshrc"
            echo "# Activate kmhelpers venv" >> "$HOME/.zshrc"
            echo "${func_line}" >> "$HOME/.zshrc"
            log_info "Added ${func_name} to ~/.zshrc"
        fi
    fi

    log_info "============================================================="
    log_info "Added command kmhelpers-activate"
    log_info "To start using kmhelpers-activate in your current bash session, run:"
    log_info ""
    log_info "source ~/.bashrc"
    log_info ""
    log_info "Or"   
    log_info ""
    log_info "source ~/.zshrc"
    log_info ""
    log_info "Or restart your shell / terminal for changes to take effect"

    log_info "============================================================="
}

# Install kmhelpers to home directory
function install_python_package()
{
    # Parse command-line options
    local use_inplace=false
    local version="${KMHELPERS_VERSION}"
    local no_alias=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --inplace)
                use_inplace=true
                shift
                ;;
            -p|--path)
                VENV_DIR="$2"
                shift 2
                ;;
            -v|--version)
                version="$2"
                shift 2
                ;;
            --no-alias)
                no_alias=true
                shift
                ;;
            *)
                log_error "Unknown option: $1"
                echo "Usage: install_python_package [--inplace] [-p|--path <VENV_DIR>] [-v|--version <version>] [--no-alias]"
                return 1
                ;;
        esac
    done

    # Find the directory where the kmhelpers package is located
    # This script should be in the kmhelpers root directory or a subdirectory
    local project_root="."

    # Check if pyproject.toml exists (indicating we're in the right directory)
    if [[ ! -f "$project_root/pyproject.toml" ]]; then
        log_info "pyproject.toml not found in current directory. Cloning kmhelpers repository..."

        # Clone repo into a temp directory
        local temp_dir=$(mktemp -d)
        trap "rm -rf '$temp_dir'" EXIT

        if ! git clone https://gitlab.inria.fr/omicfinder/kmhelpers.git "$temp_dir"; then
            log_error "Failed to clone kmhelpers repository"
            return 1
        fi

        # Checkout specified version/branch
        log_info "Checking out version: ${version}"
        if ! git -C "$temp_dir" checkout "$version"; then
            log_error "Failed to checkout kmhelpers version: ${version}"
            return 1
        fi

        project_root="$temp_dir"
        log_info "Repository cloned to: ${project_root}"
    fi

    log_info "Installing kmhelpers Python package from: ${project_root}"

    # Check if Python is available
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed or not in PATH"
        return 1
    fi

    # Install in current environment or create venv
    if [[ "$use_inplace" == true ]]; then
        log_info "Installing in current Python environment (editable mode)"

        # Check if pip is available
        if ! command -v pip &> /dev/null; then
            log_error "pip is not installed or not in PATH"
            return 1
        fi

        if pip install -e "$project_root"; then
            log_info "✓ Successfully installed kmhelpers Python package"
            log_info "You can now use 'kmhelpers' command"
            log_info "Try: kmhelpers -h"
            return 0
        else
            log_error "Failed to install kmhelpers Python package with pip"
            return 1
        fi
    else
        log_info "Creating virtual environment at: ${VENV_DIR}"

        # Create venv
        if ! python3 -m venv "${VENV_DIR}"; then
            log_error "Failed to create virtual environment at ${VENV_DIR}"
            return 1
        fi

        # Activate venv and install
        log_info "Activating virtual environment..."
        # shellcheck disable=SC1091
        source "${VENV_DIR}/bin/activate" || return 1

        log_info "Installing Python package in editable mode..."
        if pip install -e "$project_root"; then
            log_info "✓ Successfully installed kmhelpers Python package"
            log_info ""
            log_info "Virtual environment created at: ${VENV_DIR}"

            # Install activation alias
            install_shell_activation_function "${VENV_DIR}" "${no_alias}"

            log_info ""
            if [[ "$no_alias" != true ]]; then
                log_info "Quick activation: Run 'kmhelpers-activate' to activate the venv"
                log_info "Or manually: source ${VENV_DIR}/bin/activate"
            else
                log_info "To activate the environment, run:"
                log_info "  source ${VENV_DIR}/bin/activate"
            fi
            log_info ""
            log_info "Then you can use 'kmhelpers' command"
            log_info "Try: kmhelpers -h"
            return 0
        else
            log_error "Failed to install kmhelpers Python package with pip"
            return 1
        fi
    fi
}

# Activate kmhelpers virtual environment
function activate_venv()
{
    # Parse command-line options
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -p|--path)
                VENV_DIR="$2"
                shift 2
                ;;
            *)
                log_error "Unknown option: $1"
                echo "Usage: activate_venv [-p|--path <VENV_DIR>]"
                return 1
                ;;
        esac
    done

    # Check if venv exists
    if [[ ! -d "$VENV_DIR" ]]; then
        log_error "Virtual environment not found at: ${VENV_DIR}"
        log_info "Did you run 'kmhelpersctl install-pykmhelpers'?"
        return 1
    fi

    # Check if activation script exists
    if [[ ! -f "${VENV_DIR}/bin/activate" ]]; then
        log_error "Activation script not found at: ${VENV_DIR}/bin/activate"
        return 1
    fi

    log_info "To activate the virtual environment, run:"
    echo "  source ${VENV_DIR}/bin/activate"

    return 0
}

# Install kmhelpers to shell configuration
function install_shell()
{
    # Check if the script exists
    if [[ ! -f "$SCRIPT_PATH" ]]; then
        log_error "kmhelpersctl.sh not found at: $SCRIPT_PATH"
        return 1
    fi

    log_info "Installing kmhelpers shell integration"

    # Copy the script
    if ! cp "$SCRIPT_PATH" "$INSTALL_PATH"; then
        log_error "Failed to copy script to: $INSTALL_PATH"
        return 1
    fi

    # Make it executable
    if ! chmod +x "$INSTALL_PATH"; then
        log_error "Failed to make $INSTALL_PATH executable"
        return 1
    fi

    log_info "Copied script to: $INSTALL_PATH"

    local env_line="export KMHELPERS_PATH=\"${KMHELPERS_PATH}\"  # kmhelpers work directory"
    local path_line="export PATH=\"${KMHELPERS_PATH}:\$PATH\"  # Add kmhelpers to PATH"
    local installed=false

    # Create environment variable line if KMHELPERS_PATH is not the default
    local default_path="${HOME}/.kmhelpers"

    # Install for bash
    if [[ -f "$HOME/.bashrc" ]]; then
        # Add alias if not already present
        if ! grep -qF "$env_line" "$HOME/.bashrc"; then
            echo "" >> "$HOME/.bashrc"
            echo "# kmhelpers shell integration" >> "$HOME/.bashrc"
            echo "$env_line" >> "$HOME/.bashrc"
            echo "$path_line" >> "$HOME/.bashrc"
            log_info "============================================================="
            log_info "Added command kmhelpersctl to ~/.bashrc"
            log_info "Added KMHELPERS_PATH environment variable: ${KMHELPERS_PATH}"
            log_info "To start using kmhelpersctl in your current bash session, run:"
            log_info ""
            log_info "source ~/.bashrc"
            log_info ""
            log_info "Or restart your shell / terminal for changes to take effect"
            log_info "============================================================="
            installed=true
        else
            log_info "kmhelpersctl already installed in ~/.bashrc"
            installed=true
        fi
    fi

    # Install for zsh
    if [[ -f "$HOME/.zshrc" ]]; then
        # Add alias if not already present
        if ! grep -qF "$env_line" "$HOME/.zshrc"; then
            echo "" >> "$HOME/.zshrc"
            echo "# kmhelpers shell integration" >> "$HOME/.zshrc"
            echo "$env_line" >> "$HOME/.zshrc"
            echo "$path_line" >> "$HOME/.zshrc"
            log_info "============================================================="
            log_info "Added command kmhelpersctl to ~/.zshrc"
            log_info "Added KMHELPERS_PATH environment variable: ${KMHELPERS_PATH}"
            log_info "To start using kmhelpersctl in your current zsh session, run:"
            log_info ""
            log_info "source ~/.zshrc"
            log_info ""
            log_info "Or restart your shell / terminal for changes to take effect"
            log_info "============================================================="
            installed=true
        else
            log_info "kmhelpersctl already installed in ~/.zshrc"
            installed=true
        fi
    fi

    if [[ "$installed" == false ]]; then
        log_error "No shell configuration files found (.bashrc or .zshrc)"
        return 1
    else
         log_info "kmhelpersctl successfully installed"
         log_info "Follow the instructions to activate it in your current shell session, or run kmhelpersctl to start using it."
    fi

    return 0
}

# Update kmhelpers from GitLab
function update()
{
    # Parse command-line options
    local version="${KMHELPERS_VERSION}"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -v|--version)
                version="$2"
                shift 2
                ;;
            *)
                log_error "Unknown option: $1"
                echo "Usage: update [-v|--version <version>]"
                return 1
                ;;
        esac
    done

    local raw_url="https://gitlab.inria.fr/omicfinder/kmhelpers/-/raw/${version}/kmhelpersctl.sh"
    local temp_file=$(mktemp)

    log_info "Updating kmhelpers from: ${raw_url}"

    if [[ ! -f "$INSTALL_PATH" ]]; then
        log_error "kmhelpersctl not found at: $INSTALL_PATH"
        log_error "Please run 'kmhelpersctl install-kmhelpersctl' first to install kmhelpersctl"
        return 1
    fi

    # Try to download using wget first (more reliable), then curl
    if command -v wget &> /dev/null; then
        if ! wget -q -O "${temp_file}" "${raw_url}"; then
            log_error "Failed to download kmhelpersctl using wget"
            rm -f "${temp_file}"
            return 1
        fi
    elif command -v curl &> /dev/null; then
        if ! curl -L "${raw_url}" -o "${temp_file}"; then
            log_error "Failed to download kmhelpersctl using curl"
            rm -f "${temp_file}"
            return 1
        fi
    else
        log_error "Neither curl nor wget found. Please install one of them."
        rm -f "${temp_file}"
        return 1
    fi

    # Verify the downloaded file is not empty and contains bash shebang
    if [[ ! -s "${temp_file}" ]]; then
        log_error "Downloaded file is empty"
        log_error "URL was: ${raw_url}"
        rm -f "${temp_file}"
        return 1
    fi

    if ! head -1 "${temp_file}" | grep -q "^#!/bin/bash"; then
        log_error "Downloaded file is invalid or corrupted"
        log_error "URL was: ${raw_url}"
        log_error "First line of downloaded file:"
        head -1 "${temp_file}" | sed 's/^/  /'
        rm -f "${temp_file}"
        return 1
    fi

    # Copy the new version
    if cp "${temp_file}" "${INSTALL_PATH}"; then
        chmod +x "${INSTALL_PATH}"
        log_info "Successfully updated kmhelpersctl"
        rm -f "${temp_file}"
        return 0
    else
        log_error "Failed to update kmhelpersctl"
        rm -f "${temp_file}"
        return 1
    fi
}

# Main interface function
function kmhelpersctl()
{
    # Initialize paths and parse command-line arguments
    init_kmhelpers_path "$@"

    # Remove -w/--workdir flags from arguments for command processing
    local args=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -w|--workdir)
                shift 2
                ;;
            *)
                args+=("$1")
                shift
                ;;
        esac
    done

    # Create ~/.kmhelpers directory
    if ! mkdir -p "$KMHELPERS_PATH"; then
        log_error "Failed to create directory: $KMHELPERS_PATH"
        return 1
    fi

    local command="${args[0]:-}"

    # Shift to remove command from args, leaving only command arguments
    if [[ ${#args[@]} -gt 0 ]]; then
        args=("${args[@]:1}")
    fi

    case "${command}" in
        register)
            register_index "${args[0]}" "${args[1]}" "${args[2]}"
            ;;
        register-all)
            register_all_indices "${args[0]}" "${args[1]}"
            ;;
        list)
            list_indices "${args[0]}"
            ;;
        search)
            search_indices "${args[0]}" "${args[1]}" "${args[@]:2}"
            ;;
        stats)
            get_registry_stats "${args[0]}"
            ;;
        size)
            get_index_size "${args[0]}"
            ;;
        check)
            check_kmindex
            ;;
        install-kmindex)
            install_kmindex "${args[@]}"
            ;;
        install-kmindex-completion)
            install_kmindex_completion
            ;;
        install-kmhelpersctl)
            install_shell
            ;;
        install-pykmhelpers)
            install_python_package "${args[@]}"
            ;;
        activate-venv)
            activate_venv "${args[@]}"
            ;;
        update-shell)
            update "${args[@]}"
            ;;
        help|-h|--help)
            help
            echo ""
            echo ""
            install_kmindex_help
            ;;
        version|--version|-v)
            version
            ;;
        "")
            help
            ;;
        *)
            log_error "Unknown command: ${command}"
            echo "Run 'kmhelpersctl help' for usage information"
            return 1
            ;;
    esac
}

# Only run main if this script is directly executed (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    kmhelpersctl "$@"
fi

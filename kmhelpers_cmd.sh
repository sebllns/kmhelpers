#!/bin/bash

# kmhelpers - Bash utility functions for k-mer index management
# Provides convenience functions for registering and managing indices

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

VERSION=0.1

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
# MAIN INTERFACE & INSTALLATION
# ============================================================================

# Print help message
function kmhelpers_help()
{
    cat <<EOF
kmhelpers v${VERSION} - Bash utility functions for k-mer index management

USAGE:
    kmhelpers [COMMAND] [OPTIONS]

COMMANDS:
    register <registry> <name> <path>      Register a single index
    register-all <registry> <directory>    Register all indices from a directory
    list <registry>                        List all registered indices
    search <registry> <pattern>            Search for indices by pattern
    stats <registry>                       Get registry statistics
    size <index_path>                      Get size of a single index
    check                                  Check if kmindex binary is available
    install-kmindex [METHOD] [OPTIONS]     Install kmindex (conda/source/clone-source)
    install                                Install kmhelpers to home directory
    update                                 Update kmhelpers from GitLab
    help                                   Show this help message
    version                                Show version information

EXAMPLES:
    kmhelpers register /path/to/registry my_index /path/to/index
    kmhelpers stats /path/to/registry
    kmhelpers search /path/to/registry "pattern" --size-filter 100
    kmhelpers install
    kmhelpers update

For more information, visit: https://gitlab.inria.fr/omicfinder/kmhelpers
EOF
}

# Print version information
function kmhelpers_version()
{
    echo "kmhelpers v${VERSION}"
}

# Install kmhelpers to home directory
function kmhelpers_install()
{
    local install_path="$HOME/.kmhelpers.sh"
    local shell_rc=""

    log_info "Installing kmhelpers to: ${install_path}"

    # Copy script to home directory
    if cp "$0" "${install_path}"; then
        log_info "Successfully copied kmhelpers to ${install_path}"
    else
        log_error "Failed to copy kmhelpers to ${install_path}"
        return 1
    fi

    # Determine which shell configuration file to use based on running shell
    # Check shell-specific variables that are set when each shell runs
    if [[ -n "${ZSH_VERSION:-}" ]]; then
        # Running in zsh
        shell_rc="$HOME/.zshrc"
    elif [[ -n "${BASH_VERSION:-}" ]]; then
        # Running in bash - use .bashrc or .bash_profile
        if [[ -f "$HOME/.bashrc" ]]; then
            shell_rc="$HOME/.bashrc"
        elif [[ -f "$HOME/.bash_profile" ]]; then
            shell_rc="$HOME/.bash_profile"
        fi
    elif [[ -f "$HOME/.zshrc" ]]; then
        shell_rc="$HOME/.zshrc"
    elif [[ -f "$HOME/.bashrc" ]]; then
        shell_rc="$HOME/.bashrc"
    elif [[ -f "$HOME/.bash_profile" ]]; then
        shell_rc="$HOME/.bash_profile"
    fi

    if [[ -z "$shell_rc" ]]; then
        log_warn "Could not find shell configuration file (.bashrc, .bash_profile, or .zshrc)"
        log_info "Add the following line to your shell configuration file:"
        echo "  . \"${install_path}\""
        return 0
    fi

    # Add source line if not already present
    local source_line=". \"${install_path}\""
    if grep -q "kmhelpers.sh" "${shell_rc}"; then
        log_info "kmhelpers already sourced in ${shell_rc}"
        return 0
    fi

    if echo "" >> "${shell_rc}" && echo "# Load kmhelpers" >> "${shell_rc}" && echo "${source_line}" >> "${shell_rc}"; then
        log_info "Added kmhelpers to ${shell_rc}"
        log_info "Run: source ${shell_rc}"
        return 0
    else
        log_error "Failed to add kmhelpers to ${shell_rc}"
        return 1
    fi
}

# Update kmhelpers from GitLab
function kmhelpers_update()
{
    local raw_url="https://gitlab.inria.fr/omicfinder/kmhelpers/-/raw/dev/v0.5.5/kmhelpers_cmd.sh"
    local install_path="$HOME/.kmhelpers.sh"
    local temp_file=$(mktemp)

    log_info "Updating kmhelpers from: ${raw_url}"

    # Try to download using curl or wget
    if command -v curl &> /dev/null; then
        if ! curl -fsSL "${raw_url}" -o "${temp_file}"; then
            log_error "Failed to download kmhelpers using curl"
            rm -f "${temp_file}"
            return 1
        fi
    elif command -v wget &> /dev/null; then
        if ! wget -qO "${temp_file}" "${raw_url}"; then
            log_error "Failed to download kmhelpers using wget"
            rm -f "${temp_file}"
            return 1
        fi
    else
        log_error "Neither curl nor wget found. Please install one of them."
        rm -f "${temp_file}"
        return 1
    fi

    # Verify the downloaded file is not empty and contains bash shebang
    if [[ ! -s "${temp_file}" ]] || ! head -1 "${temp_file}" | grep -q "^#!/bin/bash"; then
        log_error "Downloaded file is invalid or corrupted"
        rm -f "${temp_file}"
        return 1
    fi

    # Copy the new version
    if cp "${temp_file}" "${install_path}"; then
        chmod +x "${install_path}"
        log_info "Successfully updated kmhelpers"
        rm -f "${temp_file}"
        return 0
    else
        log_error "Failed to update kmhelpers"
        rm -f "${temp_file}"
        return 1
    fi
}

# Main interface function
function kmhelpers()
{
    local command="${1:-}"

    case "${command}" in
        register)
            register_index "$2" "$3" "$4"
            ;;
        register-all)
            register_all_indices "$2" "$3"
            ;;
        list)
            list_indices "$2"
            ;;
        search)
            search_indices "$2" "$3" "${@:4}"
            ;;
        stats)
            get_registry_stats "$2"
            ;;
        size)
            get_index_size "$2"
            ;;
        check)
            check_kmindex
            ;;
        install-kmindex)
            kmhelpers_install_kmindex "${@:2}"
            ;;
        install)
            kmhelpers_install
            ;;
        update)
            kmhelpers_update
            ;;
        help|-h|--help)
            kmhelpers_help
            ;;
        version|--version|-v)
            kmhelpers_version
            ;;
        install-kmindex-help)
            kmhelpers_install_kmindex_help
            ;;
        "")
            kmhelpers_help
            ;;
        *)
            log_error "Unknown command: ${command}"
            echo "Run 'kmhelpers help' for usage information"
            return 1
            ;;
    esac
}

# ============================================================================
# KMINDEX INSTALLATION
# ============================================================================

# Install kmindex using conda
function install_kmindex_conda()
{
    local env_name="${1:-kmindex_env}"

    log_info "Installing kmindex via conda in environment: ${env_name}"

    if ! command -v conda &> /dev/null; then
        log_error "conda not found. Install Miniconda or Anaconda first."
        return 1
    fi

    # Create environment if it doesn't exist
    if ! conda env list | grep -q "^${env_name} "; then
        log_info "Creating conda environment: ${env_name}"
        if ! conda create -y -n "${env_name}"; then
            log_error "Failed to create conda environment"
            return 1
        fi
    else
        log_info "Using existing conda environment: ${env_name}"
    fi

    # Install kmindex from bioconda
    log_info "Installing kmindex from bioconda..."
    if conda run -n "${env_name}" conda install -y -c bioconda kmindex; then
        log_info "Successfully installed kmindex in ${env_name}"
        log_info "To use kmindex, activate the environment:"
        echo "  conda activate ${env_name}"
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

    if git clone --recursive https://github.com/tlemane/kmindex "${target_dir}"; then
        log_info "Successfully cloned kmindex to: ${target_dir}"
        return 0
    else
        log_error "Failed to clone kmindex repository"
        return 1
    fi
}

# Main kmindex installation function
function kmhelpers_install_kmindex()
{
    local method="${1:-conda}"
    local env_or_path="${2:-.}"
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
            log_info "Repository cloned. To build, run:"
            echo "  kmhelpers install_kmindex source ${target_dir} Release 256 8 0"
            return 0
            ;;
        *)
            log_error "Unknown installation method: ${method}"
            return 1
            ;;
    esac
}

# Print install_kmindex help
function kmhelpers_install_kmindex_help()
{
    cat <<EOF
kmindex Installation Options

USAGE:
    kmhelpers install_kmindex [METHOD] [OPTIONS]

METHODS:

    conda [ENV_NAME]
        Install kmindex from bioconda
        ENV_NAME: conda environment name (default: kmindex_env)

        Example:
          kmhelpers install_kmindex conda
          kmhelpers install_kmindex conda myenv

    source <SOURCE_DIR> [BUILD_TYPE] [MAX_KMER] [THREADS] [TESTS] [PORTABLE]
        Build and install kmindex from source
        SOURCE_DIR: path to kmindex repository
        BUILD_TYPE: Release or Debug (default: Release)
        MAX_KMER: maximum k-mer size (default: 256, must be multiple of 32)
        THREADS: build threads (default: 8)
        TESTS: 0=no tests, 1=compile tests, 2=run tests (default: 0)
        PORTABLE: ON or OFF for portable x86-64 build (default: OFF)

        Example:
          kmhelpers install_kmindex source /path/to/kmindex
          kmhelpers install_kmindex source /path/to/kmindex Release 256 8 2

    clone-source [TARGET_DIR]
        Clone kmindex repository from GitHub
        TARGET_DIR: where to clone (default: current directory)

        Example:
          kmhelpers install_kmindex clone-source
          kmhelpers install_kmindex clone-source ./kmindex_repo

EXAMPLES:

    # Install from conda (easiest)
    kmhelpers install_kmindex conda

    # Clone and build from source
    kmhelpers install_kmindex clone-source ./kmindex
    kmhelpers install_kmindex source ./kmindex Release 256 8 2

    # Build existing kmindex source directory
    kmhelpers install_kmindex source ~/src/kmindex Release

For more information, visit: https://github.com/tlemane/kmindex
EOF
}

# Only run main if this script is directly executed (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    kmhelpers "$@"
fi
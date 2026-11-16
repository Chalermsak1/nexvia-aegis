cmake_minimum_required(VERSION 3.20)
project(AegisKernel VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

include_directories(include)

# Shared kernel library
add_library(aegis_kernel SHARED
    src/aegis/csrc/aegis_kernel.cpp
)

target_compile_options(aegis_kernel PRIVATE
    -O3
    -Wall
    -Wextra
    -pedantic
)

# CTest Suite
enable_testing()

add_executable(test_nmpc_kernel
    tests/cpp/test_nmpc_kernel.cpp
)

target_link_libraries(test_nmpc_kernel PRIVATE aegis_kernel)

add_test(NAME NmpcKernelCTest COMMAND test_nmpc_kernel)

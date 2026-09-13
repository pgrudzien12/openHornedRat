cmake_minimum_required(VERSION 3.20)

project(open_horned_rat_engine LANGUAGES CXX)

find_package(OpenGL REQUIRED)
find_path(SDL2_INCLUDE_DIR SDL.h PATH_SUFFIXES SDL2 REQUIRED)
find_library(SDL2_LIBRARY NAMES SDL2 REQUIRED)

add_executable(horned-rat-engine engine/src/main.cpp)
target_compile_features(horned-rat-engine PRIVATE cxx_std_20)
target_include_directories(horned-rat-engine PRIVATE ${SDL2_INCLUDE_DIR})
target_link_libraries(horned-rat-engine PRIVATE ${SDL2_LIBRARY} OpenGL::GL)

if(MSVC)
    target_compile_options(horned-rat-engine PRIVATE /W4 /permissive-)
else()
    target_compile_options(horned-rat-engine PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()

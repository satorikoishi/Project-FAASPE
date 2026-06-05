cmake_minimum_required(VERSION 3.10)
project(jkv)

# Set C++ standard to C++17
set(CMAKE_CXX_STANDARD 17)
if(CMAKE_BUILD_TYPE STREQUAL "Release")
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -Werror -Wno-unused -Wno-sign-compare -O3")
else()
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -Werror -Wno-unused -Wno-sign-compare -O0 -g -DDBG -fsanitize=undefined -fsanitize=address -fsanitize=leak")
endif()

find_package(Protobuf CONFIG REQUIRED)
message(STATUS "Using protobuf ${Protobuf_VERSION}")
set(_PROTOBUF_LIBPROTOBUF protobuf::libprotobuf)

set(PROTO_DIR ${CMAKE_SOURCE_DIR}/proto)
set(GENERATED_PROTO_DIR ${CMAKE_BINARY_DIR}/generated)
file(MAKE_DIRECTORY ${GENERATED_PROTO_DIR})

if(CMAKE_CROSSCOMPILING)
find_program(_PROTOBUF_PROTOC protoc)
else()
set(_PROTOBUF_PROTOC $<TARGET_FILE:protobuf::protoc>)
endif()
set(jkv_proto ${PROTO_DIR}/jkv.proto)
set(jkv_proto_srcs "${GENERATED_PROTO_DIR}/jkv.pb.cc")
set(jkv_proto_hdrs "${GENERATED_PROTO_DIR}/jkv.pb.h")
add_custom_command(
      OUTPUT "${jkv_proto_srcs}" "${jkv_proto_hdrs}"
      COMMAND ${_PROTOBUF_PROTOC}
      ARGS --cpp_out "${GENERATED_PROTO_DIR}"
        -I "${PROTO_DIR}"
        "${jkv_proto}"
      DEPENDS "${jkv_proto}")

set(jkv_proto_python "${CMAKE_SOURCE_DIR}/pyclient/jkv_pb2.py")
add_custom_command(
    OUTPUT "${jkv_proto_python}"
    COMMAND ${_PROTOBUF_PROTOC}
    ARGS --python_out "${CMAKE_SOURCE_DIR}/pyclient"
        -I "${PROTO_DIR}"
        "${jkv_proto}"
    DEPENDS "${jkv_proto}"
)

# Include the source directories
include_directories(${Protobuf_INCLUDE_DIRS} ${CMAKE_CURRENT_BINARY_DIR} ${CMAKE_SOURCE_DIR}/src ${GENERATED_PROTO_DIR})
link_directories($ENV{HOME}/.local/lib)
link_directories(/usr/lib/x86_64-linux-gnu)

add_library(jkv_lib_proto
  ${jkv_proto_srcs}
  ${jkv_proto_hdrs})
target_link_libraries(jkv_lib_proto 
${_PROTOBUF_LIBPROTOBUF})

# Ensure the Python file is generated as part of your build
add_custom_target(generate_proto ALL DEPENDS "${jkv_proto_python}")

set(COMMON_SOURCE_FILES
    src/client/kv_client.cpp
    src/util/zmq_util.cpp
)

set(SERVER_SOURCE_FILES
    src/main.cpp
    src/store/kvstore.cpp
    src/store/occkvs.cpp
    src/communication/zmq_server.cpp
)

# Add the lww kvs executables
add_executable(jkv_server ${SERVER_SOURCE_FILES} ${COMMON_SOURCE_FILES} ${PROTO_SRCS} ${PROTO_HDRS})
target_link_libraries(jkv_server jkv_lib_proto zmq ${Protobuf_LIBRARIES} spdlog fmt config++)

# Add the occ kvs executables
add_executable(occ_server ${SERVER_SOURCE_FILES} ${COMMON_SOURCE_FILES} ${PROTO_SRCS} ${PROTO_HDRS})
target_link_libraries(occ_server jkv_lib_proto zmq ${Protobuf_LIBRARIES} spdlog fmt config++)
target_compile_definitions(occ_server PRIVATE USE_OCC)

# Add the source files
set(ZMQ_PINGPONG_SOURCE_FILES
    src/client/zmq_pingpong.cpp
)

add_executable(ping_client ${ZMQ_PINGPONG_SOURCE_FILES} ${COMMON_SOURCE_FILES} ${PROTO_SRCS} ${PROTO_HDRS})
target_link_libraries(ping_client jkv_lib_proto zmq ${Protobuf_LIBRARIES} spdlog fmt config++)

add_executable(occ_client ${ZMQ_PINGPONG_SOURCE_FILES} ${COMMON_SOURCE_FILES} ${PROTO_SRCS} ${PROTO_HDRS})
target_link_libraries(occ_client jkv_lib_proto zmq ${Protobuf_LIBRARIES} spdlog fmt config++)
target_compile_definitions(occ_client PRIVATE USE_OCC)

set(CACHE_SOURCE_FILES
    src/cache/cache.cpp
    src/cache/occ_cache.cpp
    src/cache/main.cpp
)

# lww cache
add_executable(cache_server ${CACHE_SOURCE_FILES} ${COMMON_SOURCE_FILES} ${PROTO_SRCS} ${PROTO_HDRS})
target_link_libraries(cache_server jkv_lib_proto zmq ${Protobuf_LIBRARIES} spdlog fmt config++)

# occ cache
add_executable(occ_cache ${CACHE_SOURCE_FILES} ${COMMON_SOURCE_FILES} ${PROTO_SRCS} ${PROTO_HDRS})
target_link_libraries(occ_cache jkv_lib_proto zmq ${Protobuf_LIBRARIES} spdlog fmt config++)
target_compile_definitions(occ_cache PRIVATE USE_OCC)

set -e

sudo apt update
sudo apt install -y autoconf automake pkg-config libtool build-essential g++ make unzip cmake protobuf-compiler libprotobuf-dev libzmq3-dev libspdlog-dev libfmt-dev libconfig++-dev

git config --global --add safe.directory ~/projects/Project-FAASPE || true

cd ~/projects/jkv

# CloudLab Ubuntu provides Protobuf through CMake's module mode rather than
# protobuf CONFIG mode. Keep the source checkout buildable after git pull.
sed -i 's/Protobuf CONFIG REQUIRED/Protobuf REQUIRED/' CMakeLists.txt
sed -i 's#^set(_PROTOBUF_LIBPROTOBUF .*#set(_PROTOBUF_LIBPROTOBUF protobuf)#' CMakeLists.txt
sed -i 's#^set(_PROTOBUF_PROTOC .*#set(_PROTOBUF_PROTOC /usr/bin/protoc)#' CMakeLists.txt

make

sudo apt update
sudo apt install -y autoconf automake pkg-config libtool build-essential g++ make unzip cmake libzmq3-dev libspdlog-dev libfmt-dev libconfig++-dev

# protobuf by grpc 1.68.0
export MY_INSTALL_DIR=$HOME/.local
mkdir -p $MY_INSTALL_DIR
echo 'export PATH=$MY_INSTALL_DIR/bin:$PATH' >> ~/.bashrc
export PATH=$MY_INSTALL_DIR/bin:$PATH
cd ~/grpc
mkdir -p cmake/build
pushd cmake/build
cmake -DgRPC_INSTALL=ON \
      -DgRPC_BUILD_TESTS=OFF \
      -DCMAKE_INSTALL_PREFIX=$MY_INSTALL_DIR \
      ../..
make -j 4
make install
popd

# build
cd ~/projects/jkv
make
.PHONY: all release debug clean

all: release

release:
	mkdir -p build && cd build && cmake -DCMAKE_BUILD_TYPE=Release ..
	cd build && make -j

debug:
	mkdir -p build && cd build && cmake -DCMAKE_BUILD_TYPE=Debug ..
	cd build && make -j

clean:
	rm -r build

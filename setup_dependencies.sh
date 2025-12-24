#!/bin/bash

# Configuration: Blender 4.1 uses Python 3.11
PY_VER="3.11"
PKG="opencv-python-headless"
TARGET_DIR="./dependencies"

# Create base directory
mkdir -p "$TARGET_DIR"

install_platform() {
    PLATFORM=$1  
    OS_NAME=$2   
    echo "--- Processing $OS_NAME ($PLATFORM) ---"
    
    mkdir -p "temp_$OS_NAME"
    mkdir -p "$TARGET_DIR/$OS_NAME"
    
    pip download \
        --dest "temp_$OS_NAME" \
        --platform "$PLATFORM" \
        --python-version "$PY_VER" \
        --implementation cp \
        --only-binary=:all: \
        --no-deps \
        "$PKG"
    
    WHEEL_FILE=$(find "temp_$OS_NAME" -name "*.whl" | head -n 1)
    
    if [ -z "$WHEEL_FILE" ]; then
        echo "Error: Failed to download wheel for $OS_NAME"
    else
        echo "Extracting $WHEEL_FILE..."
        unzip -q "$WHEEL_FILE" -d "temp_$OS_NAME/extracted"
        
        # Move 'cv2' folder
        rm -rf "$TARGET_DIR/$OS_NAME/cv2"
        mv "temp_$OS_NAME/extracted/cv2" "$TARGET_DIR/$OS_NAME/cv2"
    fi
    rm -rf "temp_$OS_NAME"
}

# Download for all platforms
install_platform "win_amd64" "win"
install_platform "manylinux_2_17_x86_64" "linux"
install_platform "macosx_11_0_arm64" "mac"

echo "Dependencies installed in $TARGET_DIR"
# Source only in this rover workspace. Keep the Ubuntu/ROS camera libraries intact.
_ROVER_CAMERA_BUILD="$HOME/rover_support/libcamera-v0.2.0-fixed/build"
_ROVER_KMS_BUILD="$HOME/rover_support/kmsxx/build"
if [ -f "$HOME/rover_support/camera_patch_build.json" ] && \
   [ -f "$_ROVER_CAMERA_BUILD/src/py/libcamera/_libcamera.so" ]; then
  export PYTHONPATH="$_ROVER_CAMERA_BUILD/src/py:$_ROVER_KMS_BUILD/py${PYTHONPATH:+:$PYTHONPATH}"
  export LD_LIBRARY_PATH="$_ROVER_CAMERA_BUILD/src/libcamera/base:$_ROVER_CAMERA_BUILD/src/libcamera${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
unset _ROVER_CAMERA_BUILD _ROVER_KMS_BUILD

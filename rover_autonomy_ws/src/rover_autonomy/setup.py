from glob import glob

from setuptools import find_packages, setup

setup(
    name="rover_autonomy",
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/rover_autonomy"]),
        ("share/rover_autonomy", ["package.xml"]),
        ("share/rover_autonomy/config", glob("config/*.yaml")),
        ("share/rover_autonomy/launch", glob("launch/*.launch.py")),
        ("share/rover_autonomy/models", glob("models/*")),
    ],
    install_requires=["setuptools"],
    zip_safe=False,
    maintainer="takyeji",
    maintainer_email="takyeji@tak.local",
    description="Camera line/sign/hand rover control",
    license="MIT",
    entry_points={
        "console_scripts": [
            "motor_bench_test = rover_autonomy.ros.motor_bench_test:main",
            "camera_node = rover_autonomy.ros.camera_node:main",
            "perception_node = rover_autonomy.ros.perception_node:main",
            "supervisor_node = rover_autonomy.ros.supervisor_node:main",
            "base_node = rover_autonomy.ros.base_node:main",
            "simulation_node = rover_autonomy.ros.simulation_node:main",
        ]
    },
)

from setuptools import setup
from glob import glob
import os

package_name = "drone_gz_bridge"

setup(
    name=package_name,
    version="0.0.1",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="polat",
    maintainer_email="polatozgur111@gmail.com",
    description="Gazebo to ROS 2 bridge configuration for warehouse drone mapping.",
    license="MIT",
    tests_require=["pytest"],
        entry_points={
        "console_scripts": [
            "odom_to_tf = drone_gz_bridge.odom_to_tf:main",
            "map_to_odom_tf = drone_gz_bridge.map_to_odom_tf:main",
            "slam_localization_bridge = drone_gz_bridge.slam_localization_bridge:main",
            "calibration_guard = drone_gz_bridge.calibration_guard:main",
            "gimbal_to_tf = drone_gz_bridge.gimbal_to_tf:main",
        ],
    },
)

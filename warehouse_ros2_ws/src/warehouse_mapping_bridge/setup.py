from glob import glob
from setuptools import find_packages, setup


package_name = "warehouse_mapping_bridge"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/launch", glob("launch/*.launch.py")),
        (f"share/{package_name}/config", glob("config/*.yaml")),
        (f"share/{package_name}/rviz", glob("rviz/*.rviz")),
        (f"share/{package_name}/worlds", glob("worlds/*.sdf")),
        (f"share/{package_name}/urdf", glob("urdf/*")),
    ],
    install_requires=[
        "setuptools",
        "fastapi>=0.100",
        "uvicorn>=0.23",
        "pymavlink>=2.4.49",
        "PyYAML>=6.0",
    ],
    zip_safe=True,
    maintainer="Drone App",
    maintainer_email="operator@example.com",
    description="Jetson-side ROS 2 and Isaac ROS bridge for warehouse 3D mapping.",
    license="Proprietary",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "warehouse_bridge_service = warehouse_mapping_bridge.bridge_service:main",
            "warehouse_artifact_exporter = warehouse_mapping_bridge.artifact_exporter_node:main",
            "warehouse_health_monitor = warehouse_mapping_bridge.health_monitor_node:main",
            "warehouse_odometry_export = warehouse_mapping_bridge.odometry_export_node:main",
            "warehouse_live_map_publisher = warehouse_mapping_bridge.live_map_publisher_node:main",
            "warehouse_vision_mavlink_bridge = warehouse_mapping_bridge.vision_mavlink_bridge_node:main",
            "warehouse_sim_tf_broadcaster = warehouse_mapping_bridge.sim_tf_broadcaster_node:main",
        ],
    },
)

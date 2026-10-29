import os
from glob import glob
from setuptools import find_packages, setup

package_name = "aegis_drone"

setup(
    name=package_name,
    version="9.7.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name] if os.path.exists("resource/" + package_name) else []),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
    ],
    install_requires=["setuptools", "numpy", "scipy"],
    zip_safe=True,
    maintainer="Chalermsak",
    maintainer_email="chalermsak@nexvia.ai",
    description="NEXVIA AEGIS: Provably Safe Autonomous AI Companion Computer Autonomy Stack for PX4 Autopilot",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "aegis_drone_node = aegis.sim2real.aegis_ros2_node:main",
        ],
    },
)

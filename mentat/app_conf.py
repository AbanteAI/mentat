from configparser import ConfigParser
from pathlib import Path

from mentat.utils import fetch_resource

conf_ini_path = Path("conf/conf.ini")

config = ConfigParser()
with fetch_resource(conf_ini_path).open("r") as conf_ini_file:
    config.read_file(conf_ini_file)

ENV_TYPE = config["environment"]["type"]
IS_DEV = ENV_TYPE == "dev"
IS_PROD = ENV_TYPE == "prod"

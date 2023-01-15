import logging, os


wd = os.path.dirname(__file__)
log_path = os.path.join(wd, "logging.txt")
logging.basicConfig(format='%(asctime)s | %(levelname)-8s | %(funcName)s() %(filename)s line=%(lineno)s | %(message)s',
                    handlers=[logging.FileHandler(log_path), logging.StreamHandler(),],
                    level=logging.INFO)

logging.info("yes, I was booting correctly")
    
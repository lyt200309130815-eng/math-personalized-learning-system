"""Legacy regression fixtures explicitly select V1, independent of app default."""
import os
from unittest.mock import patch


def use_v1_test_config(test):
    environment = patch.dict(os.environ, {'ACTIVE_TAXONOMY_VERSION': 'function_v1'})
    environment.start()
    test.addCleanup(environment.stop)

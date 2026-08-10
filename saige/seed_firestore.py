# Compatibility shim — implementation lives in integrations.firestore_seed
from integrations.firestore_seed import *  # noqa: F401,F403

if __name__ == "__main__":
    import runpy

    runpy.run_module("integrations.firestore_seed", run_name="__main__")

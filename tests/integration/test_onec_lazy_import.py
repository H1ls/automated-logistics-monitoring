import subprocess
import sys

class TestOneCPackageImport:

    def test_package_import_does_not_eagerly_import_bot(self):
        code = "import sys; import LogistX.onec; assert 'LogistX.onec.bot' not in sys.modules"
        result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr

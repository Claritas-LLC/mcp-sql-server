import unittest
from unittest.mock import patch

from mcp_sqlserver import server


class TestReportStorage(unittest.TestCase):
    def test_persist_report_creates_directory_before_write(self):
        with patch("pathlib.Path.mkdir", autospec=True) as mock_mkdir, \
            patch("pathlib.Path.write_text", autospec=True, return_value=10) as mock_write_text:
            server._persist_report_html("abc123", "<html>ok</html>")

        mock_mkdir.assert_called_once_with(server._REPORT_STORAGE_DIR, parents=True, exist_ok=True)
        mock_write_text.assert_called_once()

    def test_persist_report_wraps_oserror_as_ioerror(self):
        with patch("pathlib.Path.mkdir", autospec=True, side_effect=OSError("read-only fs")):
            with self.assertRaisesRegex(OSError, "Failed to persist report"):
                server._persist_report_html("abc123", "<html>ok</html>")


if __name__ == "__main__":
    unittest.main()

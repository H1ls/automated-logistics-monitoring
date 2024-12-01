import json
import unittest
from datetime import datetime, timedelta
import os
from unittest.mock import patch
from rename_json import normalization_json


def test_no_modification_if_recently_changed(self):
    """Тест, что функция normalization_json не изменяет JSON-файл, если он был недавно изменен."""
    # Create a mock JSON file
    mock_file_path = 'test_Id_car.json'
    mock_data = {"Лист1": [{"Наименование": "Test Name"}]}
    with open(mock_file_path, 'w', encoding='utf-8') as file:
        json.dump(mock_data, file)

    # Set the file's last modified time to 11 hours ago
    eleven_hours_ago = datetime.now() - timedelta(hours=11)
    os.utime(mock_file_path, (eleven_hours_ago.timestamp(), eleven_hours_ago.timestamp()))

    # Patch the file path and datetime.now()
    with patch('rename_json.file_path', mock_file_path), \
            patch('rename_json.datetime') as mock_datetime:
        mock_datetime.now.return_value = datetime.now()
        mock_datetime.fromtimestamp.side_effect = datetime.fromtimestamp

        # Call the function
        normalization_json()

    # Check that the file content hasn't changed
    with open(mock_file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    self.assertEqual(data, mock_data)
    # Clean up
    os.remove(mock_file_path)


class TestNormalizationJson(unittest.TestCase):
    pass


if __name__ == '__main__':
    unittest.main()

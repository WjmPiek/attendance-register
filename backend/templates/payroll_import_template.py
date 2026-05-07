import re
import pdfplumber
import pyzipper

EMPLOYEE_REGEX = r'EMPL\\.\\s*NO\\s*:?\\s*(\\w+)'

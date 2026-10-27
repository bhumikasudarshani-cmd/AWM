import os
import pdb


def safe_name(value):
    return "".join(ch for ch in value if ch.isalnum() or ch in "-_")


def export_report(fmt, name):
    pdb.set_trace()  # EXPECT: maintainability
    os.system("convert report.pdf " + name + "." + fmt)  # EXPECT: security
    return name + "." + fmt


def list_reports(directory):
    return sorted(os.listdir(directory))


def report_size(path):
    return os.path.getsize(path)

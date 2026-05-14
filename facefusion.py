#!/usr/bin/env python3

import ctypes
import os
import sys

os.environ['OMP_NUM_THREADS'] = '1'

from facefusion import conda, core


def setup_windows_process_cleanup() -> None:
	"""
	On Windows, bind current process to a Job Object with
	JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, so child processes are
	terminated when this process exits (including console close).
	"""
	if sys.platform != 'win32':
		return

	# Constants from WinNT.h / WinBase.h
	JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
	JobObjectExtendedLimitInformation = 9

	class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
		_fields_ = [
			('PerProcessUserTimeLimit', ctypes.c_longlong),
			('PerJobUserTimeLimit', ctypes.c_longlong),
			('LimitFlags', ctypes.c_uint32),
			('MinimumWorkingSetSize', ctypes.c_size_t),
			('MaximumWorkingSetSize', ctypes.c_size_t),
			('ActiveProcessLimit', ctypes.c_uint32),
			('Affinity', ctypes.c_size_t),
			('PriorityClass', ctypes.c_uint32),
			('SchedulingClass', ctypes.c_uint32)
		]

	class IO_COUNTERS(ctypes.Structure):
		_fields_ = [
			('ReadOperationCount', ctypes.c_uint64),
			('WriteOperationCount', ctypes.c_uint64),
			('OtherOperationCount', ctypes.c_uint64),
			('ReadTransferCount', ctypes.c_uint64),
			('WriteTransferCount', ctypes.c_uint64),
			('OtherTransferCount', ctypes.c_uint64)
		]

	class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
		_fields_ = [
			('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),
			('IoInfo', IO_COUNTERS),
			('ProcessMemoryLimit', ctypes.c_size_t),
			('JobMemoryLimit', ctypes.c_size_t),
			('PeakProcessMemoryUsed', ctypes.c_size_t),
			('PeakJobMemoryUsed', ctypes.c_size_t)
		]

	try:
		kernel32 = ctypes.WinDLL('kernel32', use_last_error = True)
		kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
		kernel32.CreateJobObjectW.restype = ctypes.c_void_p
		kernel32.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
		kernel32.SetInformationJobObject.restype = ctypes.c_int
		kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
		kernel32.AssignProcessToJobObject.restype = ctypes.c_int
		kernel32.GetCurrentProcess.argtypes = []
		kernel32.GetCurrentProcess.restype = ctypes.c_void_p

		job_handle = kernel32.CreateJobObjectW(None, None)
		if not job_handle:
			return

		extended_info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
		extended_info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
		if not kernel32.SetInformationJobObject(
			job_handle,
			JobObjectExtendedLimitInformation,
			ctypes.byref(extended_info),
			ctypes.sizeof(extended_info)
		):
			return

		current_process_handle = kernel32.GetCurrentProcess()
		kernel32.AssignProcessToJobObject(job_handle, current_process_handle)
	except Exception:
		# Best-effort only, keep startup behavior unchanged on failure.
		return


if __name__ == '__main__':
	setup_windows_process_cleanup()
	conda.setup()
	core.cli()

"""Create files with an owner-only Windows DACL before writing secrets."""

from __future__ import annotations

import ctypes
import errno
import msvcrt
import os
from ctypes import wintypes
from pathlib import Path

_TOKEN_QUERY = 0x0008
_TOKEN_USER = 1
_ERROR_INSUFFICIENT_BUFFER = 122
_SDDL_REVISION = 1
_GENERIC_WRITE = 0x40000000
_READ_CONTROL = 0x00020000
_SE_FILE_OBJECT = 1
_OWNER_AND_DACL = 0x00000001 | 0x00000004
_CREATE_NEW = 1
_FILE_ATTRIBUTE_NORMAL = 0x0080
_FILE_PERSISTENT_ACLS = 0x0008
_INVALID_HANDLE = wintypes.HANDLE(-1).value


class _TokenUser(ctypes.Structure):
    # TOKEN_USER contains one SID_AND_ATTRIBUTES.
    _fields_ = [("sid", wintypes.LPVOID), ("attributes", wintypes.DWORD)]


class _SecurityAttributes(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.DWORD),
        ("descriptor", wintypes.LPVOID),
        ("inherit_handle", wintypes.BOOL),
    ]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

_kernel32.GetCurrentProcess.argtypes = ()
_kernel32.GetCurrentProcess.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
_kernel32.CloseHandle.restype = wintypes.BOOL
_kernel32.LocalFree.argtypes = (wintypes.HLOCAL,)
_kernel32.LocalFree.restype = wintypes.HLOCAL
_kernel32.CreateFileW.argtypes = (
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.POINTER(_SecurityAttributes),
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
)
_kernel32.CreateFileW.restype = wintypes.HANDLE
_kernel32.GetVolumeInformationByHandleW.argtypes = (
    wintypes.HANDLE,
    wintypes.LPWSTR,
    wintypes.DWORD,
    wintypes.LPDWORD,
    wintypes.LPDWORD,
    wintypes.LPDWORD,
    wintypes.LPWSTR,
    wintypes.DWORD,
)
_kernel32.GetVolumeInformationByHandleW.restype = wintypes.BOOL
_advapi32.OpenProcessToken.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.HANDLE),
)
_advapi32.OpenProcessToken.restype = wintypes.BOOL
_advapi32.GetTokenInformation.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.LPDWORD,
)
_advapi32.GetTokenInformation.restype = wintypes.BOOL
_advapi32.ConvertSidToStringSidW.argtypes = (
    wintypes.LPVOID,
    ctypes.POINTER(wintypes.LPWSTR),
)
_advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
_advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = (
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.LPVOID),
    wintypes.LPDWORD,
)
_advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
_advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = (
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.LPWSTR),
    wintypes.LPDWORD,
)
_advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = wintypes.BOOL
_advapi32.GetSecurityInfo.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.LPVOID),
    ctypes.POINTER(wintypes.LPVOID),
    ctypes.POINTER(wintypes.LPVOID),
    ctypes.POINTER(wintypes.LPVOID),
    ctypes.POINTER(wintypes.LPVOID),
)
_advapi32.GetSecurityInfo.restype = wintypes.DWORD


def _current_user_sid() -> str:
    token = wintypes.HANDLE()
    if not _advapi32.OpenProcessToken(
        _kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        size = wintypes.DWORD()
        _advapi32.GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(size))
        error = ctypes.get_last_error()
        if error != _ERROR_INSUFFICIENT_BUFFER:
            raise ctypes.WinError(error)
        buffer = ctypes.create_string_buffer(size.value)
        if not _advapi32.GetTokenInformation(
            token, _TOKEN_USER, buffer, size.value, ctypes.byref(size)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        sid = wintypes.LPWSTR()
        if not _advapi32.ConvertSidToStringSidW(
            _TokenUser.from_buffer(buffer).sid, ctypes.byref(sid)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return sid.value
        finally:
            _kernel32.LocalFree(ctypes.cast(sid, wintypes.HLOCAL))
    finally:
        _kernel32.CloseHandle(token)


def _supports_persistent_acls(handle: int) -> bool:
    flags = wintypes.DWORD()
    if not _kernel32.GetVolumeInformationByHandleW(
        handle, None, 0, None, None, ctypes.byref(flags), None, 0
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return bool(flags.value & _FILE_PERSISTENT_ACLS)


def _owner_and_dacl(descriptor: wintypes.LPVOID) -> tuple[str, bool, str]:
    sddl = wintypes.LPWSTR()
    if not _advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
        descriptor, _SDDL_REVISION, _OWNER_AND_DACL, ctypes.byref(sddl), None
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        owner, _, dacl = sddl.value.partition("D:")
        flags, _, access_entries = dacl.partition("(")
        # Windows can add auto-inheritance flags to a protected DACL.
        return owner, "P" in flags, access_entries
    finally:
        _kernel32.LocalFree(ctypes.cast(sddl, wintypes.HLOCAL))


def _file_owner_and_dacl(handle: int) -> tuple[str, bool, str]:
    descriptor = wintypes.LPVOID()
    error = _advapi32.GetSecurityInfo(
        handle,
        _SE_FILE_OBJECT,
        _OWNER_AND_DACL,
        None,
        None,
        None,
        None,
        ctypes.byref(descriptor),
    )
    if error:
        raise ctypes.WinError(error)
    try:
        return _owner_and_dacl(descriptor)
    finally:
        _kernel32.LocalFree(descriptor)


def open_private_file(path: Path) -> int:
    """Exclusively create a file with a protected DACL and return its descriptor."""

    if ":" in path.name:
        raise OSError(errno.EINVAL, "Private key output cannot be a named stream", path)
    sid = _current_user_sid()
    descriptor = wintypes.LPVOID()
    # P disables DACL inheritance and FA grants file access to this SID only.
    if not _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        f"O:{sid}D:P(A;;FA;;;{sid})", _SDDL_REVISION, ctypes.byref(descriptor), None
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        expected_acl = _owner_and_dacl(descriptor)
        attributes = _SecurityAttributes(
            ctypes.sizeof(_SecurityAttributes), descriptor, 0
        )
        handle = _kernel32.CreateFileW(
            str(path),
            _GENERIC_WRITE | _READ_CONTROL,
            0,
            ctypes.byref(attributes),
            _CREATE_NEW,
            _FILE_ATTRIBUTE_NORMAL,
            None,
        )
        if handle == _INVALID_HANDLE:
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        _kernel32.LocalFree(descriptor)

    try:
        if not _supports_persistent_acls(handle):
            raise OSError(
                errno.ENOTSUP, "Private key output requires persistent ACLs", path
            )
        # Some filesystem policies (such as EFS) can change the requested DACL.
        if _file_owner_and_dacl(handle) != expected_acl:
            raise PermissionError(
                errno.EACCES, "Private key file does not have an owner-only ACL", path
            )
        return msvcrt.open_osfhandle(
            handle, os.O_WRONLY | os.O_BINARY | os.O_NOINHERIT
        )
    except BaseException:
        _kernel32.CloseHandle(handle)
        path.unlink(missing_ok=True)
        raise

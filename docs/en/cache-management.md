# UV Cache Management Guide

> v3.0 note: this self-use fork is installed from source with `uv sync`,
> and the daemon is launched via
> `uv run mcp-interactive-feedback serve --http` from the cloned repo.
> Stop the daemon (Ctrl+C) before running cache cleanup, or use `--force`
> which attempts to terminate related processes first.

## 🔍 Problem Description

`uv sync` and any transient `uvx` usage both populate `~/.cache/uv/`.
Over time, that cache can consume significant disk space — especially
if you frequently rebuild the environment or switch between multiple
uv tools.

### Cache Location
- **Windows**: `%USERPROFILE%\AppData\Local\uv\cache`
- **macOS/Linux**: `~/.cache/uv`

## 🧹 Cleanup Methods

### Method 1: Using UV Built-in Commands (Recommended)

```bash
# Check cache location
uv cache dir

# Clean all cache
uv cache clean
```

### Method 2: Using Project-Provided Cleanup Tool

```bash
# Check cache size
python scripts/cleanup_cache.py --size

# Preview cleanup content
python scripts/cleanup_cache.py --dry-run

# Execute cleanup
python scripts/cleanup_cache.py --clean

# Force cleanup (attempts to close related processes)
python scripts/cleanup_cache.py --force
```

## ⚠️ Common Issues

### Issue: "File is being used by another process" error during cleanup

**Cause**: The MCP feedback daemon or other uvx processes are running

**Solutions**:
1. **Close related processes**:
   - Stop the daemon (`Ctrl+C` in the terminal where it was launched,
     or `kill $(cat ~/.config/mcp-feedback-enhanced/daemon.pid)`)
   - Close any Cursor / Claude / other AI agents that may still have
     MCP sessions open
   - Terminate all `uvx` related processes

2. **Use force cleanup**:
   ```bash
   python scripts/cleanup_cache.py --force
   ```

3. **Manual cleanup**:
   ```bash
   # Windows
   taskkill /f /im uvx.exe
   taskkill /f /im python.exe /fi "WINDOWTITLE eq *mcp-feedback-enhanced*"

   # Then execute cleanup
   uv cache clean
   ```

### Issue: Cache grows large again quickly after cleanup

**Cause**: Repeated `uv sync --upgrade` runs, or running many unrelated
`uvx` tools, each of which may re-resolve dependencies and expand the
cache.

**Recommendations**:
1. **Regular cleanup**: Recommend weekly or monthly cleanup
2. **Monitor size**: Regularly check cache size
3. **Pin deps**: Keep `uv.lock` up to date to reduce re-resolution churn

## 📊 Cache Size Monitoring

### Check Cache Size

```bash
# Using cleanup tool
python scripts/cleanup_cache.py --size

# Or check directory size directly (Windows)
dir "%USERPROFILE%\AppData\Local\uv\cache" /s

# macOS/Linux
du -sh ~/.cache/uv
```

### Recommended Cleanup Frequency

| Cache Size | Recommended Action |
|-----------|-------------------|
| < 100MB   | No cleanup needed |
| 100MB-500MB | Consider cleanup |
| > 500MB   | Cleanup recommended |
| > 1GB     | Cleanup strongly recommended |

## 🔧 Automated Cleanup

### Windows Scheduled Task

```batch
@echo off
cd /d "G:\github\interactive-feedback-mcp"
python scripts/cleanup_cache.py --clean
```

### macOS/Linux Cron Job

```bash
# Weekly cleanup on Sunday
0 2 * * 0 cd /path/to/interactive-feedback-mcp && python scripts/cleanup_cache.py --clean
```

## 💡 Best Practices

1. **Regular monitoring**: Check cache size monthly
2. **Timely cleanup**: Clean when cache exceeds 500MB
3. **Close processes**: Ensure related MCP services are closed before cleanup
4. **Backup important data**: Ensure important projects are backed up before cleanup

## 🆘 Troubleshooting

### Common Causes of Cleanup Failure

1. **Process occupation**: the `serve --http` daemon (or another uvx
   process) is still running
2. **Insufficient permissions**: Administrator privileges required
3. **Disk errors**: File system errors

### Resolution Steps

1. Stop the daemon (Ctrl+C / kill PID in `daemon.pid`) and close any
   AI-agent clients that may still hold MCP sessions
2. Run cleanup command as administrator
3. If still failing, restart computer and try again
4. Consider manually deleting parts of cache directory

## 📞 Support

If you encounter cleanup issues, please:
1. Check the troubleshooting section in this document
2. Report issues on [GitHub Issues](https://github.com/0xlane/mcp-interactive-feedback-multi-session/issues)
3. Provide error messages and system information

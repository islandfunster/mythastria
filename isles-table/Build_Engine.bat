@echo off
setlocal
cd /d "%~dp0"
where cargo >nul 2>nul
if errorlevel 1 (
  echo Rust cargo was not found. Install the Rust toolchain first.
  pause
  exit /b 1
)
cargo test --manifest-path engine\Cargo.toml --locked
if errorlevel 1 exit /b 1
cargo build --manifest-path engine\Cargo.toml --locked --release --target wasm32-unknown-unknown
if errorlevel 1 exit /b 1
copy /y "engine\target\wasm32-unknown-unknown\release\isles_engine.wasm" "dist\isles_engine.wasm"
echo Engine rebuilt. Refresh the browser to load it.
endlocal

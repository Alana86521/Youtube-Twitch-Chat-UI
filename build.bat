@echo off

echo Checking for required Python libraries...

set packages=tkinter requests pytchat pytz

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed or not in PATH
    pause
    exit /b 1
)

for %%p in (%packages%) do (
    echo Checking for %%p...
    python -c "import %%p" >nul 2>&1
    if %errorlevel% neq 0 (
        echo Installing %%p...
        pip install %%p
        if %errorlevel% neq 0 (
            echo Failed to install %%p
            pause
            exit /b 1
        )
    )
)

echo All required packages are installed.
echo Building executable with PyInstaller...

pyinstaller --onefile --windowed --name "Twitch And Youtube Chat" --icon=icon.ico main.py

if %errorlevel% neq 0 (
    echo PyInstaller build failed
    pause
    exit /b 1
)

echo Build completed successfully!
echo The executable should be in the 'dist' folder.
pause
cd /d %USERPROFILE%\obituary-watch
call venv\Scripts\activate
git add -A
git commit -m "v3: simplified — paste Wikipedia link, see person card, click Watch"
git push origin master
echo.
echo Done!
pause

cd /d %USERPROFILE%\obituary-watch
call venv\Scripts\activate
git add -A
git commit -m "new UI: live search autocomplete, React-style pills, static CSS/JS"
git push origin master
echo.
echo Done! All changes saved to GitHub.
pause

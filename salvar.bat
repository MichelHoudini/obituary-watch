cd /d %USERPROFILE%\obituary-watch
call venv\Scripts\activate
git add -A
git commit -m "search results page: Wikidata-powered, living people only, single occupation, pagination"
git push origin master
echo.
echo Done! Changes saved to GitHub.
pause

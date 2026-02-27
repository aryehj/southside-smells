# TL; DR
Between October 7 and November 3, 2025, neighbors in Hyde Park and surrounding areas submitted 39 smell reports via a Google Form hosted by Aryeh Jacobsohn, who lives in Hyde Park and smelled the smell. Most described a burning plastic or chemical smell. This analysis correlates those reports with hourly wind direction, wind speed, and barometric pressure data to to infer where the smell might be coming from and reason about the quality of the evidence. 

## Methods
The bulk of the analysis is reproducing in a Jupyter Notebook shared in this repository, with a few secondary Python scripts and the data files they generated shared so that anyone from the community can reproduce most of this analysis without (for example) needing to obtain API keys. 

1. Self-reported survey administered via Google Forms to the Good Neighbors email list. In other words, not a random sample.
2. Survey data exported as CSV.
3. Email addresses removed manually by author. 
4. LLM (Claude.ai) used to map self-reported approximate location in the form of cross stress, to approximate latitude and longitude.
5. LLM used to layer in data on weather, wind direction, PM2, etc. from public data sources.
6. Bulk of analysis shared for reproduction in a Jupyter Notebook in this repository (tested working on author's M1 Mac using Miniconda and uv).

Survey data available on request. As the data contain submitters' approximate locations, I did not feel comfortable giving unrestricted access to the file. 

## Unsolved Problems
- What to do next (working on this).
- Layering in summary research on health effects of the pollutants we believe are contained in the plume that reaches Hyde Park.
- Layering in citations and data linking specific smells cited to probable origins. 

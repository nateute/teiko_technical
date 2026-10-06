# The Teiko Code Problem
Hello! This is Nate Hansen's solution to the Teiko code assignment associated with the job listing for Bioinformatics Engineer. The code is built to run quite easily based on the instructions in the form.

## Running the Code
To run the pipeline, simply leverage the makefile through the following terminal commands at the root directory:

`make setup`
`make pipeline`
`make dashboard`

Then, access the interactive dashboard at http://localhost:5173 in your browser. To exit the dashboard, close the browser tab and use `ctrl + C` in the active terminal.

## Notes
I made a few design decisions throughout.
- Interface design is more of an art than a science, and I am very adaptable with feedback to standardize visualizations.
- For the statistical comparisons (Part 3), I stratified the comparisons by study timepoint. This seemed like the strongest way to show statistical effect between the responders/non-responders, though it was not asked for explicitly.
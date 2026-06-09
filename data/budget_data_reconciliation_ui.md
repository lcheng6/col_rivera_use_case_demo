## Create Synthetic Data



We are going to do some iterative development on creating the logic and ui construct to automate budget reconciliation, with this page to track decisions, todo items, and their status


### Background
I want to make a MVP in Python Streamlit to help with a difficult task for the user. He has two databases that doesn't talk to each other, that are tracking the ongoing expenditures of the same organization.  Because they are two different systems, the same dollar might be tracked in different categories and subcategories.  For the user, a tool that can quickly reconciliate spending categories across the two systems would be extremely useful.  In another word, the user would like a tool that would solve this question:
  * sum(spending category or categories from system 1) per year ~= sum (spending category or categories from system 2) of the same year
  * Narrow the member of the categories for each system as much as possible. 
  * The category names of both system in a match are probably semantically similar, so some kind of rank and stacking of possible solution groupings would be helpful.  

### Tasks
I want you, Claude to create two subagents that research and plan approaches first.  
   1. First agent to research the best logic to solve this type of problem
   2. Second agent to assist with a design of an application interface where users are given feedback from the candidate solution from budget reconciliation and can guide and manually edit groupings toward a final solution.  



### Status
THis file is written by me (JYOTHI KUMAR), where I discuss more about the journey, decisions took, reasoning behind it!

# CORE ARCHITECTURE
we should use diff agents, of free tier in order to get the ouput.. there are 2 main things to solve with the given Constraints

1. Extraction of the data properly without errors/loss.. if my base data itself is corrupt, then it will effect the final results
2. Strategic passsing of the context across the agents. 

This is a 3 step process in total - 
DATA EXTRACTION -> SANITY AGENTS CHECK -> FRAUD AGENTS CHECK

We can't pass all data to single agent, and here, almost all agents are free/small parameter models. So can't expect them to do heavy/intelligent tasks. 

## IDEATING : 

1. For extraction, we can take images and extract data from the llm.. but again evaluating llm response + passing each page as img will surpass the rate-limit
   
2. As its PDF, we can extract data page-wise, where we have page wise text. If we detect images, then we send that image to vision model for extraction of crutial data.

### KEY DECISION - 
I extracted page summaries + tagged that page into one of the tags ["METHODOLOGY","RESULT"....]

This helped in strategic passing of those content pages only to specific agents saving time & cost.

NEXT CONSTRAINT - 16k token usage.
Basically, if we take some 15-30 pages of research, that itself will cost like 20k tokens including textual + image parsed data.

Using that on all agents is bad. Not all agents need the text data.

So, we extact page_summaries, which has the crutial data analyzed from that page. 

Here, we just reduced our dependency

Afer this, we process through diff agents with diff methodologies.

The final prompts, approaches are written post checking, validating the results... to get optimized factual results with minimal hallucinations.


CORE PROBLEM FACED - 
1. Grammar agent - because it was english/format check, this agent used to hallucinate a lot in order to perform... took 5 prompt iterations
2. Novelty check - we use google gemini web search tool + prompt... the issue is rate limits here. This is the only step we don't have any fallbacks.. cause no other provider gives web search for free!

And also, it used to hallucinate by citing new papers which are released post the input paper... as an issue. Handling that hallucination was a task!

3. Consistency check - The core issue was, earlier I was passing summaries, so it could not co-relate much from these.. later I started passing few tagged pages only, so that we can get the accurate result rather than passing whole content!

On whole, per agent prompt iterations took 2-3, but above agents took more!


Really had fun building... The output is accurate, like overall above 80% reliability!

The only issue was, as I used free-tier models, I ran out of rate-limits pretty fast, taking more time to experiment towards better results!

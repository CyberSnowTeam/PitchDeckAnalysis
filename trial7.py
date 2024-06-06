from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from openai import OpenAI
from dotenv import load_dotenv, set_key
from pymongo import MongoClient
from urllib.parse import quote_plus
import os
import certifi

load_dotenv()

key = os.getenv("OPENAI_API_KEY")
assistant_id = os.getenv("ASSISTANT_ID")

client = OpenAI(api_key=key)

# MongoDB setup
db_username = quote_plus('SujitSankar')
db_password = quote_plus('Sujit@123')
uri = f'mongodb+srv://{db_username}:{db_password}@pitchdeckdb.99abzt5.mongodb.net/?retryWrites=true&w=majority&tls=true&tlsAllowInvalidCertificates=true'
mongo_client = MongoClient(uri, tlsCAFile=certifi.where())

db = mongo_client['pitchdeckdb']
collection = db['user_data']

app = FastAPI()

description = """You are an Investor Analyst Bot. Your main job is to generate a report like how an investor analyst would."""

instructions = """You'll be given a Pitch Deck of a company that contains all the information about the company. Your main job is to understand all the instructions and give a structured response
The main function you possess is when the user asks to generate a report You must generate a report about the company in a specific format. The format must be

Default Format(Let this be the default format for any report generation)
    
    <b>Company Summary</b>
    Give a long summary of the company. It should be in a paragraph format of about eight lines.
        
    <b>Founder Overview</b>
    Check how many founders or co-founders are there.
    For each person mention their name in a separate bullet point along with their designation and below that mention their background, what they have done in the past and how many years of expertise they have as a paragraph.

    <b>Fundamentals of underlying technology</b>
    Identify the technologies used in the product or service provided by the company. Mention them as sequential points with numerical numbering.
    1.[Technology 1]
    [Explanation of the technology in terms of a long paragraph]
    2.[Technology 2]
    [Explanation of the technology in terms of a long paragraph]
    .
    .
    .etc.
    Take each technology and explain it extensively.
    Under each technology or feature give an explanation of what it is and how it is used in the product or service. Give a very detailed explanation as to how the technology works and how it is integrated.
    I need big paragraphs of at least 10 lines explaining each technology. Even if the content is small make sure the explanation is done in detail.

    <b>Product and use case overview</b>
    Explain how the product is used in real world and how the end user can use the product. Explain how the end user can benefit from this product and also explain any limitations it may contain according to your analysis. Explain everything the product does.
    The explanation should be very detailed and in the form of a paragraph of at least 10 sentences.

    <b>Go to market</b>
    Explain the target customers and the market the product or service is aimed for. Explain in detail how the company is getting these customers.
    The explanation should be in detail, in a paragraph format of at least 10 sentences.

    <b>Market Analysis</b>
        • Market size: [Insert numerical data]
        • Growth trends: [Describe qualitatively]
        • Competition analysis: [Describe qualitatively]
        • Opportunities: [Describe qualitatively]
        • Market share: [Insert numerical data]
        • Growth projections: [Insert numerical data]

    <b>Founders' Background</b>
        • Qualifications: [Describe qualitatively]
        • Experience: [Describe qualitatively]
        • Past successes: [Insert numerical data]
        • Industry recognition: [Describe qualitatively]"""

def create_user_session():
    vector_store = client.beta.vector_stores.create(name="Pitch Deck")
    set_key('.env', 'VECTOR_ID', vector_store.id)

    thread = client.beta.threads.create()
    return vector_store.id, thread.id

@app.post("/create_user/")
async def create_user(name: str = Form(...), company_name: str = Form(...), mobile_no: str = Form(...)):
    user_id = str(os.urandom(16).hex())
    vector_store_id, thread_id = create_user_session()
    collection.insert_one({
        "user_id": user_id,
        "name": name,
        "company_name": company_name,
        "mobile_no": mobile_no,
        "vector_store_id": vector_store_id,
        "thread_id": thread_id,
        "sessions": []
    })
    return JSONResponse(content={"user_id": user_id, "vector_store_id": vector_store_id, "thread_id": thread_id})

@app.post("/create_new_session/")
async def create_new_session(background_tasks: BackgroundTasks, user_id: str = Form(...), company_name: str = Form(...), file: UploadFile = File(...)):
    user_data = collection.find_one({"user_id": user_id})
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")

    vector_store_id = user_data['vector_store_id']
    thread_id = user_data['thread_id']

    file_path = f"uploads/{file.filename}"
    with open(file_path, "wb") as f:
        f.write(await file.read())

    background_tasks.add_task(upload_pitch_deck, vector_store_id, file_path)
    background_tasks.add_task(update_assistant, [vector_store_id])

    collection.update_one(
        {"user_id": user_id},
        {"$set": {"pitchdeck": file_path, "company_name": company_name}}
    )

    # Generate summary
    summary = await generate_summary(vector_store_id, thread_id, file_path)
    print(f"Generated summary with vector_store_id: {vector_store_id} and thread_id: {thread_id}")

    return JSONResponse(content={"user_id": user_id, "vector_store_id": vector_store_id, "thread_id": thread_id, "summary": summary})

def upload_pitch_deck(vector_store_id, file_path):
    with open(file_path, "rb") as file_stream:
        file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vector_store_id,
            files=[file_stream]
        )

def update_assistant(vector_store_ids):
    client.beta.assistants.update(
        assistant_id=assistant_id,
        tool_resources={"file_search": {"vector_store_ids": vector_store_ids}},
    )

async def generate_summary(vector_store_id, thread_id, file_path):
    summary_prompt = """
    You are an investment analyst at a large VC firm. Your job is to analyze pitch decks and documents shared by startups, infer information about them, and write a comprehensive summary. Review each slide/page of the provided document and write a detailed summary about the startup, including all key data. Maintain a formal business tone, and focus extensively on the numbers.
    Sections to include:
    1. Company Overview: Provide a brief introduction to the company, including its mission, vision, and key products/services.
    2. Product Range and Market Positioning: Describe the company's product lineup, target market segments, and unique selling propositions. Highlight any innovative features or competitive advantages.
    3. Financial Performance: Analyze the company's financial data, including revenue growth, gross margins, and profitability. Compare these metrics with industry benchmarks and competitors, if applicable.
    4. Customer Acquisition and Retention: Detail the company's customer acquisition strategies, retention rates, and any notable marketing tactics or programs.
    5. Market Opportunity: Assess the overall market potential for the company's products/services. Include relevant industry trends, market size, and growth projections.
    6. Expansion Plans: Outline the company's plans for geographic and product expansion. Include projected revenue growth and strategic initiatives.
    7. Risk Assessment: Conduct a thorough risk assessment, covering legal, product, competitive, regulatory, and revenue risks. Ignore any category if there are no significant risks.
    8. Growth Potential: Evaluate the company's potential for future growth based on market trends and the company's strategic plans. Provide a reasoned analysis of why the company will grow or fail.
    9. Related News and Market Significance: Provide links and headlines of related news, articles, blogs, surveys, or websites that highlight the significance of the company or market. Include any notable mentions of the company in articles or magazines. This should include information that supports the company's potential or market trends.
    10. Conclusion and Opinion: Based on the provided data, offer your opinion on the company/deal. Discuss the strengths and potential concerns, and conclude with a recommendation. Ensure each point is detailed with mini-paragraphs rather than brief statements. The goal is to produce a well-rounded and thorough analysis that aids in making informed investment decisions.
    """

    message = client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=summary_prompt,
    )

    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread_id, assistant_id=assistant_id
    )

    messages = list(client.beta.threads.messages.list(thread_id=thread_id, run_id=run.id))
    summary_content = messages[0].content[0].text

    return summary_content.value

@app.post("/chat/")
async def chat_with_assistant(user_id: str = Form(...), user_input: str = Form(...)):
    user_data = collection.find_one({"user_id": user_id})
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")

    vector_store_id = user_data['vector_store_id']
    thread_id = user_data['thread_id']

    message = client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_input,
    )

    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread_id, assistant_id=assistant_id
    )

    messages = list(client.beta.threads.messages.list(thread_id=thread_id, run_id=run.id))
    message_content = messages[0].content[0].text
    return JSONResponse(content={"response": message_content.value})

@app.post("/generate_report/")
async def generate_report(user_id: str = Form(...), subheadings: list[str] = Form(...)):
    user_data = collection.find_one({"user_id": user_id})
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")

    vector_store_id = user_data['vector_store_id']
    thread_id = user_data['thread_id']

    report_content = ""
    for option in subheadings:
        report_content += get_report_section(option)

    if not report_content:
        raise HTTPException(status_code=400, detail="Invalid subheadings provided.")

    final_instructions = instructions + report_content
    assistant = client.beta.assistants.create(
        name="Pitch Deck Analysis Bot",
        description=description,
        instructions=final_instructions,
        model="gpt-4o",
        tools=[{"type": "file_search"}]
    )

    assistant = client.beta.assistants.update(
        assistant_id=assistant.id,
        tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}},
    )

    thread = client.beta.threads.create()

    message = client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content="Generate a report based on the PitchDeck in the default format given.",
    )

    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id, assistant_id=assistant.id
    )

    messages = list(client.beta.threads.messages.list(thread_id=thread.id, run_id=run.id))
    message_content = messages[0].content[0].text

    formatted_report = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
            .section {{ margin-bottom: 20px; }}
            .section h2 {{ color: #2F4F4F; }}
        </style>
    </head>
    <body>
        {message_content}
    </body>
    </html>
    """

    return JSONResponse(content={"report": formatted_report})

def get_report_section(option: str) -> str:
    report_section = ""
    if option == "Go-to-Market Strategy":
        report_section = """
        <b>Go-to-Market Strategy</b>
            • Target audience: [Describe qualitatively]
            • Marketing strategies: [Describe qualitatively]
            • Partnerships: [Describe qualitatively]
            • Customer acquisition costs: [Insert numerical data]
            • Conversion rates: [Insert numerical data]
        """
    elif option == "Market Analysis":
        report_section = """
        <b>Market Analysis</b>
            • Market size: [Insert numerical data]
            • Growth trends: [Describe qualitatively]
            • Competition analysis: [Describe qualitatively]
            • Opportunities: [Describe qualitatively]
            • Market share: [Insert numerical data]
            • Growth projections: [Insert numerical data]
        """
    elif option == "Founders' Background":
        report_section = """
        <b>Founders' Background</b>
            • Qualifications: [Describe qualitatively]
            • Experience: [Describe qualitatively]
            • Past successes: [Insert numerical data]
            • Industry recognition: [Describe qualitatively]
        """
    elif option == "Customer Feedback":
        report_section = """
        <b>Customer Feedback</b>:
            • Satisfaction metrics: [Insert numerical data]
            • Retention rates: [Insert numerical data]
        """
    elif option == "Risk Assessment":
        report_section = """
        <b>Risk Assessment</b>
            • Risk factors:
            • List specific risk factors and explain their potential impact.
            • Include numerical data on risk mitigation strategies and their effectiveness.
            • Regulatory Issues: [Describe qualitatively]
        """
    elif option == "Performance Metrics":
        report_section = """
        <b>Performance Metrics</b>
            • Key metrics:
            • Revenue growth: [Insert numerical data]
            • Profitability: [Insert numerical data]
            • Customer acquisition cost: [Insert numerical data]
            • Market share: [Insert numerical data]
            • Benchmarking:
            • Performance gaps: [Insert numerical data]
            • Improvement targets: [Insert numerical data]
        """
    elif option == "Strategic Analysis":
        report_section = """
        <b>Strategic Analysis</b>
            • SWOT Analysis:
            • Strengths: [Describe qualitatively]
            • Weaknesses: [Describe qualitatively]
            • Opportunities: [Describe qualitatively]
            • Threats: [Describe qualitatively]
            • Market positioning: [Insert numerical data]
            • Competitive advantages: [Insert numerical data]
        """
    return report_section

@app.get("/")
async def main():
    content = """
    <body>
    <h2>Create User</h2>
    <form id="createUserForm" method="post">
        <input name="name" type="text" placeholder="Name">
        <input name="company_name" type="text" placeholder="Company Name">
        <input name="mobile_no" type="text" placeholder="Mobile No">
        <input type="submit" value="Create User">
    </form>
    <br>
    <h2>Create New Session</h2>
    <form id="createSessionForm" enctype="multipart/form-data" method="post">
        <input id="sessionUserId" name="user_id" type="hidden">
        <input name="company_name" type="text" placeholder="Company Name">
        <input name="file" type="file">
        <input type="submit" value="Create Session">
    </form>
    <br>
    <h2>Chat with Assistant</h2>
    <form id="chatForm" method="post">
        <input id="chatUserId" name="user_id" type="hidden">
        <input name="user_input" type="text" placeholder="Your question">
        <input type="submit" value="Send">
    </form>
    <br>
    <h2>Generate Report</h2>
    <form id="reportForm" method="post">
        <input id="reportUserId" name="user_id" type="hidden">
        <div>
            <input type="checkbox" name="subheadings" value="Go-to-Market Strategy"> Go-to-Market Strategy<br>
            <input type="checkbox" name="subheadings" value="Market Analysis"> Market Analysis<br>
            <input type="checkbox" name="subheadings" value="Founders' Background"> Founders' Background<br>
            <input type="checkbox" name="subheadings" value="Customer Feedback"> Customer Feedback<br>
            <input type="checkbox" name="subheadings" value="Risk Assessment"> Risk Assessment<br>
            <input type="checkbox" name="subheadings" value="Performance Metrics"> Performance Metrics<br>
            <input type="checkbox" name="subheadings" value="Strategic Analysis"> Strategic Analysis<br>
        </div>
        <input type="submit" value="Generate">
    </form>
    <div id="chatBox"></div>
    
    <script>
    document.getElementById('createUserForm').onsubmit = async function(event) {
        event.preventDefault();
        let formData = new FormData(document.getElementById('createUserForm'));
        let response = await fetch('/create_user/', {
            method: 'POST',
            body: formData
        });
        let result = await response.json();
        document.getElementById('sessionUserId').value = result.user_id;
        document.getElementById('chatUserId').value = result.user_id;
        document.getElementById('reportUserId').value = result.user_id;
        document.getElementById('chatBox').innerHTML += "<p>User created successfully. User ID: " + result.user_id + "</p>";
    };

    document.getElementById('createSessionForm').onsubmit = async function(event) {
        event.preventDefault();
        let formData = new FormData(document.getElementById('createSessionForm'));
        let response = await fetch('/create_new_session/', {
            method: 'POST',
            body: formData
        });
        let result = await response.json();
        document.getElementById('chatBox').innerHTML += "<p>Session created successfully. User ID: " + result.user_id + ", Vector Store ID: " + result.vector_store_id + ", Thread ID: " + result.thread_id + "</p><p><strong>Summary:</strong> " + result.summary + "</p>";
    };

    document.getElementById('chatForm').onsubmit = async function(event) {
        event.preventDefault();
        let formData = new FormData(document.getElementById('chatForm'));
        let response = await fetch('/chat/', {
            method: 'POST',
            body: formData
        });
        let result = await response.json();
        document.getElementById('chatBox').innerHTML += "<p><strong>You:</strong> " + formData.get('user_input') + "</p>";
        document.getElementById('chatBox').innerHTML += "<p><strong>AI:</strong> " + result.response + "</p>";
    };

    document.getElementById('reportForm').onsubmit = async function(event) {
        event.preventDefault();
        let formData = new FormData(document.getElementById('reportForm'));
        let response = await fetch('/generate_report/', {
            method: 'POST',
            body: formData
        });
        let result = await response.json();
        document.getElementById('chatBox').innerHTML += result.report;
    };
    </script>
    </body>
    """
    return HTMLResponse(content=content)

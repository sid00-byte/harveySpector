const fs = require("fs");
const path = require("path");

const SITE_URL = "https://harvey-spector-mr3f75ep9-sid00-bytes-projects.vercel.app";
const BACKEND_URL = "https://harveyspector-nq1f.onrender.com";
const SAMPLE_FILE_PATH = "/Users/siddharth/harveySpector/sample_board_resolution.docx";

async function runTest() {
  console.log("🚀 Starting Exhaustive Live Site End-to-End Test...");
  console.log(`Frontend URL: ${SITE_URL}`);
  console.log(`Backend URL:  ${BACKEND_URL}`);
  
  if (!fs.existsSync(SAMPLE_FILE_PATH)) {
    console.error(`❌ Error: Sample file not found at ${SAMPLE_FILE_PATH}`);
    return;
  }

  try {
    // 1. Sign In via Better Auth API
    console.log("\n1. Signing in to live site...");
    const loginRes = await fetch(`${SITE_URL}/api/auth/sign-in/email`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Origin": SITE_URL
      },
      body: JSON.stringify({
        email: "anusharma@gmail.com",
        password: "Anu@1234"
      })
    });

    if (!loginRes.ok) {
      const errText = await loginRes.text();
      throw new Error(`Login failed (HTTP ${loginRes.status}): ${errText}`);
    }

    const loginData = await loginRes.json();
    console.log("✅ Signed in successfully. User Info:", JSON.stringify(loginData.user));

    // Capture session cookies
    const cookieHeader = loginRes.headers.get("set-cookie");
    if (!cookieHeader) {
      console.warn("⚠️ Warning: No set-cookie header returned. Session tracking may fail if the cookies are not set.");
    }
    
    // Parse cookies from headers to pass them in subsequent requests
    const cookies = loginRes.headers.getSetCookie 
      ? loginRes.headers.getSetCookie().map(c => c.split(";")[0]).join("; ")
      : cookieHeader ? cookieHeader.split(";")[0] : "";
    
    console.log(`✅ Session Cookies captured: ${cookies ? cookies.substring(0, 50) + "..." : "None"}`);

    const headersWithAuth = {
      "Cookie": cookies,
      "Content-Type": "application/json",
      "Origin": SITE_URL
    };

    // 2. Fetch Cases (Dashboard state)
    console.log("\n2. Fetching dashboard cases...");
    const casesRes = await fetch(`${SITE_URL}/api/cases`, {
      headers: headersWithAuth
    });

    if (!casesRes.ok) {
      const errText = await casesRes.text();
      throw new Error(`Failed to fetch cases (HTTP ${casesRes.status}): ${errText}`);
    }

    const casesData = await casesRes.json();
    console.log(`✅ Dashboard loaded. Found ${casesData.cases ? casesData.cases.length : 0} existing cases.`);

    // 3. Initialize new Case on Next.js Server
    console.log("\n3. Initializing new compliance case on live frontend...");
    const fileStats = fs.statSync(SAMPLE_FILE_PATH);
    const newCaseRes = await fetch(`${SITE_URL}/api/cases`, {
      method: "POST",
      headers: headersWithAuth,
      body: JSON.stringify({
        title: `E2E Live Test - ${new Date().toLocaleTimeString()}`,
        description: "Exhaustive programmatic live site validation run",
        fileName: "sample_board_resolution.docx",
        fileType: "docx",
        fileSizeBytes: fileStats.size
      })
    });

    if (!newCaseRes.ok) {
      const errText = await newCaseRes.text();
      throw new Error(`Failed to create case (HTTP ${newCaseRes.status}): ${errText}`);
    }

    const newCaseData = await newCaseRes.json();
    const caseId = newCaseData.case.id;
    const documentId = newCaseData.case.documents[0].id;
    console.log(`✅ Case initialized. Case ID: ${caseId}, Document ID: ${documentId}`);

    // 4. Upload Document to Render Backend
    console.log("\n4. Uploading document to Render FastAPI backend...");
    const fileBuffer = fs.readFileSync(SAMPLE_FILE_PATH);
    const fileBlob = new Blob([fileBuffer], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
    const formData = new FormData();
    formData.append("file", fileBlob, "sample_board_resolution.docx");

    const uploadRes = await fetch(`${BACKEND_URL}/api/v1/documents/upload`, {
      method: "POST",
      body: formData
    });

    if (!uploadRes.ok) {
      const errText = await uploadRes.text();
      throw new Error(`Backend upload failed (HTTP ${uploadRes.status}): ${errText}`);
    }

    const uploadData = await uploadRes.json();
    const fastapiDocId = uploadData.document_id;
    console.log(`✅ Backend processed document. Doc ID: ${fastapiDocId}`);

    // 5. Trigger Analysis on Render Backend
    console.log("\n5. Triggering compliance analysis on Render backend...");
    const analyzeRes = await fetch(`${BACKEND_URL}/api/v1/analyze/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ document_id: fastapiDocId })
    });

    if (!analyzeRes.ok) {
      const errText = await analyzeRes.text();
      throw new Error(`Backend analysis trigger failed (HTTP ${analyzeRes.status}): ${errText}`);
    }

    const analyzeData = await analyzeRes.json();
    const fastapiAnalysisId = analyzeData.analysis_id;
    console.log(`✅ Analysis started. Analysis ID: ${fastapiAnalysisId}, Status: ${analyzeData.status}`);

    // 6. Save Analysis Placeholder on Next.js Server
    console.log("\n6. Saving analysis placeholder to PostgreSQL database...");
    const savePlaceholderRes = await fetch(`${SITE_URL}/api/cases/${caseId}/analysis`, {
      method: "POST",
      headers: headersWithAuth,
      body: JSON.stringify({
        complianceScore: null,
        report: null,
        requiredForms: [],
        status: "processing",
        documentId: documentId,
        analysisId: fastapiAnalysisId
      })
    });

    if (!savePlaceholderRes.ok) {
      const errText = await savePlaceholderRes.text();
      throw new Error(`Failed to save analysis placeholder (HTTP ${savePlaceholderRes.status}): ${errText}`);
    }
    console.log("✅ Analysis placeholder successfully saved in DB.");

    // 7. Polling status until completed
    console.log("\n7. Polling case detail API for background RAG completion...");
    let completed = false;
    let attempts = 0;
    const maxAttempts = 30; // 30 * 4s = 120s max wait time
    
    while (!completed && attempts < maxAttempts) {
      attempts++;
      console.log(`   [Attempt ${attempts}/${maxAttempts}] Checking case status...`);
      
      const checkRes = await fetch(`${SITE_URL}/api/cases/${caseId}`, {
        headers: headersWithAuth
      });

      if (!checkRes.ok) {
        const errText = await checkRes.text();
        throw new Error(`Error during polling check (HTTP ${checkRes.status}): ${errText}`);
      }

      const checkData = await checkRes.json();
      const currentCase = checkData.case;
      console.log(`   Current Status: ${currentCase.status}`);
      
      if (currentCase.status === "completed") {
        completed = true;
        const analysis = currentCase.analyses[0];
        console.log("\n🎉 --- LIVE E2E SUCCESSFUL ---");
        console.log(`Case Title:       ${currentCase.title}`);
        console.log(`Case ID:          ${currentCase.id}`);
        console.log(`Analysis Status:  ${analysis.status}`);
        console.log(`Compliance Score: ${analysis.complianceScore}%`);
        console.log(`Required Forms:   ${analysis.requiredForms.join(", ")}`);
        
        const report = analysis.report;
        const warnings = report.items.filter(i => {
          const s = i.status?.toUpperCase();
          return s === "WARNING" || s === "NEEDS_REVIEW";
        }).length;
        const issues = report.items.filter(i => i.status?.toUpperCase() === "NON_COMPLIANT").length;
        
        console.log(`Findings parsed:  ${issues} Issues, ${warnings} Warnings / Needs Review`);
        console.log("-----------------------------\n");
        break;
      } else if (currentCase.status === "failed") {
        throw new Error("Analysis failed on backend server.");
      }

      // Wait 4 seconds before checking again
      await new Promise(resolve => setTimeout(resolve, 4000));
    }

    if (!completed) {
      throw new Error("Polling timed out before analysis could complete.");
    }

    // 8. Test the Chat Feature on Render Backend
    console.log("\n8. Testing the chat feature on Render backend...");
    const chatMsg = "What are the rules for related party transactions under the Act?";
    const chatRes = await fetch(`${BACKEND_URL}/api/v1/chat/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        case_id: caseId,
        message: chatMsg,
        history: []
      })
    });

    if (!chatRes.ok) {
      const errText = await chatRes.text();
      throw new Error(`Chat API request failed (HTTP ${chatRes.status}): ${errText}`);
    }

    const chatData = await chatRes.json();
    console.log(`✅ Chat response received successfully.`);
    console.log(`💬 Reply excerpt: ${chatData.reply.substring(0, 150)}...`);

    // 9. Fetch Chat History
    console.log("\n9. Fetching chat history from Render backend...");
    const historyRes = await fetch(`${BACKEND_URL}/api/v1/chat/history/${caseId}`);
    if (!historyRes.ok) {
      const errText = await historyRes.text();
      throw new Error(`Chat history request failed (HTTP ${historyRes.status}): ${errText}`);
    }

    const historyData = await historyRes.json();
    console.log(`✅ Chat history retrieved. Messages count: ${historyData.total_messages}`);
    if (historyData.total_messages >= 2) {
      console.log("   - User Message:      " + historyData.messages[0].content);
      console.log("   - Assistant Message: " + historyData.messages[1].content.substring(0, 100) + "...");
    } else {
      throw new Error("Chat history is missing expected messages.");
    }
    
    console.log("\n🎉 ALL E2E AND CHAT CHECKS COMPLETED SUCCESSFULLY!");

  } catch (error) {
    console.error("\n❌ LIVE E2E TEST FAILED WITH ERROR:", error);
  }
}

runTest();

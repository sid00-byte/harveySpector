import { NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { headers } from "next/headers";
import prisma from "@/lib/prisma";

export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const session = await auth.api.getSession({
      headers: await headers(),
    });

    if (!session?.user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { id } = await params;

    const caseRecord = await prisma.case.findFirst({
      where: {
        id,
        userId: session.user.id,
      },
      include: {
        documents: true,
      },
    });

    if (!caseRecord) {
      return NextResponse.json({ error: "Case not found" }, { status: 404 });
    }

    const {
      complianceScore,
      report,
      requiredForms,
      status, // "completed" | "failed" | "processing"
      documentId,
      analysisId,
    } = await req.json();

    // Update case status and optional tags
    const tags = requiredForms || [];
    let caseStatus = "failed";
    if (status === "completed") caseStatus = "completed";
    else if (status === "processing") caseStatus = "analyzing";

    await prisma.case.update({
      where: { id },
      data: {
        status: caseStatus,
        tags: {
          set: tags,
        },
      },
    });

    // Determine document ID to link
    const targetDocId = documentId || caseRecord.documents[0]?.id;

    if (targetDocId) {
      await prisma.document.update({
        where: { id: targetDocId },
        data: {
          status: status === "completed" ? "completed" : status === "processing" ? "processing" : "failed",
        },
      });
    }

    // Create Analysis record
    const newAnalysis = await prisma.analysis.create({
      data: {
        id: analysisId || undefined, // Use custom FastAPI analysis ID
        caseId: id,
        documentId: targetDocId || null,
        status: status === "completed" ? "completed" : status === "processing" ? "processing" : "failed",
        complianceScore: complianceScore !== undefined && complianceScore !== null ? parseFloat(complianceScore) : null,
        report: report || null,
        requiredForms: requiredForms || [],
      },
    });

    return NextResponse.json({ analysis: newAnalysis });
  } catch (error) {
    console.error("Error creating analysis report:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}

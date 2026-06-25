import { NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { headers } from "next/headers";
import prisma from "@/lib/prisma";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function GET(
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

    let caseRecord = await prisma.case.findFirst({
      where: {
        id,
        userId: session.user.id,
      },
      include: {
        documents: true,
        analyses: {
          orderBy: {
            createdAt: "desc",
          },
          take: 1,
        },
      },
    });

    if (!caseRecord) {
      return NextResponse.json({ error: "Case not found" }, { status: 404 });
    }

    // Server-side polling integration: If case status is still analyzing, check FastAPI backend
    const latestAnalysis = caseRecord.analyses?.[0];
    if (
      (caseRecord.status === "analyzing" || caseRecord.status === "pending") &&
      latestAnalysis &&
      latestAnalysis.status === "processing"
    ) {
      const fastapiAnalysisId = latestAnalysis.id;
      
      try {
        const checkRes = await fetch(`${API_URL}/api/v1/analyze/analysis/${fastapiAnalysisId}`);
        if (checkRes.ok) {
          const checkData = await checkRes.json();
          
          if (checkData.status === "COMPLETED") {
            // Fetch the completed report
            const reportRes = await fetch(`${API_URL}/api/v1/analyze/analysis/${fastapiAnalysisId}/report`);
            if (reportRes.ok) {
              const reportData = await reportRes.json();
              
              // Persist report data into database
              await prisma.$transaction([
                prisma.case.update({
                  where: { id },
                  data: {
                    status: "completed",
                    tags: reportData.required_forms || [],
                  },
                }),
                prisma.document.update({
                  where: { id: latestAnalysis.documentId || "" },
                  data: { status: "completed" },
                }),
                prisma.analysis.update({
                  where: { id: fastapiAnalysisId },
                  data: {
                    status: "completed",
                    complianceScore: reportData.compliance_score !== undefined ? parseFloat(reportData.compliance_score) : null,
                    report: reportData,
                    requiredForms: reportData.required_forms || [],
                  },
                }),
              ]);

              // Reload the updated case
              const updatedCase = await prisma.case.findFirst({
                where: { id, userId: session.user.id },
                include: {
                  documents: true,
                  analyses: {
                    orderBy: { createdAt: "desc" },
                    take: 1,
                  },
                },
              });
              if (updatedCase) {
                caseRecord = updatedCase;
              }
            }
          } else if (checkData.status === "FAILED") {
            // Persist failure status
            await prisma.$transaction([
              prisma.case.update({
                where: { id },
                data: { status: "failed" },
              }),
              prisma.document.update({
                where: { id: latestAnalysis.documentId || "" },
                data: { status: "failed" },
              }),
              prisma.analysis.update({
                where: { id: fastapiAnalysisId },
                data: { status: "failed" },
              }),
            ]);

            // Reload the updated case
            const updatedCase = await prisma.case.findFirst({
              where: { id, userId: session.user.id },
              include: {
                documents: true,
                analyses: {
                  orderBy: { createdAt: "desc" },
                  take: 1,
                },
              },
            });
            if (updatedCase) {
              caseRecord = updatedCase;
            }
          }
        }
      } catch (err) {
        console.error("Error polling FastAPI backend:", err);
      }
    }

    return NextResponse.json({ case: caseRecord });
  } catch (error) {
    console.error("Error fetching case detail:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}

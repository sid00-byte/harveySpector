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

    // Verify case belongs to user
    const caseRecord = await prisma.case.findFirst({
      where: {
        id,
        userId: session.user.id,
      },
    });

    if (!caseRecord) {
      return NextResponse.json({ error: "Case not found" }, { status: 404 });
    }

    const { fileName, fileType, fileSizeBytes } = await req.json();

    if (!fileName) {
      return NextResponse.json({ error: "fileName is required" }, { status: 400 });
    }

    // Create new document under this case
    const document = await prisma.document.create({
      data: {
        caseId: id,
        fileName,
        fileType: fileType || "text",
        fileSizeBytes: fileSizeBytes || 0,
        status: "processing",
      },
    });

    // Update case status to analyzing since a new file is being processed
    await prisma.case.update({
      where: { id },
      data: {
        status: "analyzing",
      },
    });

    return NextResponse.json({ document });
  } catch (error) {
    console.error("Error attaching document to case:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}

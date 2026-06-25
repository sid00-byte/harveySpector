import { NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { headers } from "next/headers";
import prisma from "@/lib/prisma";

export async function GET() {
  try {
    const session = await auth.api.getSession({
      headers: await headers(),
    });

    if (!session?.user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const cases = await prisma.case.findMany({
      where: {
        userId: session.user.id,
      },
      orderBy: {
        createdAt: "desc",
      },
      include: {
        analyses: {
          orderBy: {
            createdAt: "desc",
          },
          take: 1,
        },
      },
    });

    return NextResponse.json({ cases });
  } catch (error) {
    console.error("Error fetching cases:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}

export async function POST(req: Request) {
  try {
    const session = await auth.api.getSession({
      headers: await headers(),
    });

    if (!session?.user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { title, description, fileName, fileType, fileSizeBytes } = await req.json();

    if (!title) {
      return NextResponse.json({ error: "Title is required" }, { status: 400 });
    }

    const newCase = await prisma.case.create({
      data: {
        title,
        description: description || "",
        userId: session.user.id,
        status: "analyzing",
        documents: {
          create: {
            fileName: fileName || "Untitled Document",
            fileType: fileType || "text",
            fileSizeBytes: fileSizeBytes || 0,
            status: "processing",
          },
        },
      },
      include: {
        documents: true,
      },
    });

    return NextResponse.json({ case: newCase });
  } catch (error) {
    console.error("Error creating case:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}

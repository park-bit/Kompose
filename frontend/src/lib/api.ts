import { ChatResponse, TravelSlots } from "@/types/travel";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function sendChatMessage(
  message: string,
  sessionId: string | null,
  slots: TravelSlots
): Promise<ChatResponse> {
  try {
    const res = await fetch(`${API_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        message,
        ...slots,
      }),
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`API error ${res.status}: ${text}`);
    }

    return await res.json();
  } catch (err: any) {
    if (err instanceof TypeError && err.message.includes("fetch")) {
      throw new Error(
        "Backend server unreachable at http://localhost:8000. Please start backend with: uvicorn app.main:app --reload"
      );
    }
    throw err;
  }
}

export async function getSessionHistory(sessionId: string) {
  try {
    const res = await fetch(`${API_URL}/api/session/${sessionId}/history`);
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

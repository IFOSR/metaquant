import { redirect } from "next/navigation";

export default async function StrategyChatRedirect({
  searchParams,
}: {
  searchParams: Promise<{ draft?: string }>;
}) {
  const { draft } = await searchParams;
  redirect(draft ? `/research/new?draft=${draft}` : "/research/new");
}

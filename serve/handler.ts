// ACP Serve: обработчик offering `provider_check`.
import type { Handler } from "acp-cli/serve/types";
import { checkProvider } from "./check";

const handler: Handler = async (input) => {
  const report = await checkProvider(input.requirements?.provider_address);
  return { deliverable: JSON.stringify(report) };
};

export default handler;

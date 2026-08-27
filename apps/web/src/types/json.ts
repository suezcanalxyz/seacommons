/** Values that may cross an HTTP, WebSocket, or storage JSON boundary. */
export type JsonPrimitive = boolean | number | string | null;

export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];

export type JsonObject = {
  [key: string]: JsonValue;
};

/** ISO-8601 timestamp serialized as JSON. */
export type IsoDateTime = string;

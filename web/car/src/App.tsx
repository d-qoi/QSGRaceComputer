import { createSignal, onMount, For, Component, createEffect } from "solid-js";

interface Alert {
  message: string;
  name: "warning" | "alert";
  value: number;
  triggered: boolean;
}

const MessageDisplay: Component<{ message: string; color: string }> = (
  props
) => {
  return <p class={`text-4xl ${props.color}`}>{props.message}</p>;
};

const AlertDisplay: Component<{ alert: Alert }> = (props) => {
  const backgroundColor =
    props.alert.name === "warning" ? "bg-yellow-500" : "bg-red-500";
  return (
    <div class={`text-4xl text-green-700 ${backgroundColor}`}>
      {props.alert.message}
    </div>
  );
};

let messageIdCounter = 0;

const App: Component = () => {
  const [messages, setMessages] = createSignal<
    { id: number; message: string; color: string }[]
  >([]);
  const [alerts, setAlerts] = createSignal<Alert[]>([]);

  const fetchData = async () => {
    try {
      const response = await fetch("/events_longpoll");
      if (response.status === 204) {
        fetchData();
        return;
      }

      const data = await response.json();
      console.log("Data:", data);
      if (data.triggered !== undefined) {
        handleAlertSSEMessage(data);
      } else {
        handleSSEMessage(data);
      }

      setTimeout(fetchData, 10);
    } catch (error) {
      console.error("Failed to fetch data:", error);
      setTimeout(fetchData, 10);
    }
  };

  createEffect(() => {
    console.log("Alerts:", alerts());
    console.log("Messages:", messages());
  });

  const handleSSEMessage = (data: {
    name: string;
    content: string;
    timeout: number;
  }) => {
    console.log("SSE Message:", data);
    if (data.content && data.name) {
      const newId = ++messageIdCounter;
      let timeout = data.timeout * 1000.0;
      setMessages((messages) =>
        [
          ...messages,
          {
            id: newId,
            message: data.content,
            color: `text-${data.name}-600`,
          },
        ].slice(-2)
      );

      console.log("Setting timeout for message with id:", newId, timeout);

      setTimeout(() => {
        console.log("Removing message with id:", newId);
        setMessages((msgs) => msgs.filter((msg) => msg.id !== newId));
      }, timeout);
      console.log("Done handling SSE message");
    }
  };

  const handleAlertSSEMessage = (data: {
    content: string;
    name: "warning" | "alert";
    value: number;
    triggered: boolean;
  }) => {
    console.log("Alert SSE Message:", data);
    setAlerts((alerts) => {
      console.log("Adding alert:", data);
      const alertIndex = alerts.findIndex(
        (alert) => alert.message === data.content
      );
      console.log("alertIndex:", alertIndex);
      if (alertIndex !== -1) {
        const updatedAlerts = [...alerts];
        updatedAlerts[alertIndex] = {
          ...updatedAlerts[alertIndex],
          name: data.name,
          value: data.value,
          triggered: data.triggered,
        };
        console.log("Updated alerts:", updatedAlerts);
        return updatedAlerts;
      } else {
        console.log("Adding alert:", data);
        return [
          {
            message: data.content, // Ensure correct access
            name: data.name,
            value: data.value,
            triggered: data.triggered,
          },
          ...alerts,
        ].filter((alert) => alert.triggered);
      }
    });
  };

  onMount(() => {
    fetchData();
  });

  return (
    <div class="flex h-screen flex-col space-y-4 p-4">
      <div class="flex flex-1 flex-col space-y-2 overflow-auto border p-2">
        <For each={messages()}>
          {(msg) => (
            <div class="flex-1 border">
              <MessageDisplay message={msg.message} color={msg.color} />
            </div>
          )}
        </For>
      </div>
      <div class="flex flex-1 flex-col space-y-2 overflow-auto border p-2">
        <For each={alerts().filter((alert) => alert.triggered)}>
          {(alert) => (
            <div class="flex-1 border">
              <AlertDisplay alert={alert} />
            </div>
          )}
        </For>
      </div>
    </div>
  );
};

export default App;

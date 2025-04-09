import { onCleanup, type Component } from "solid-js";

const MessageDisplay: Component<{ message: string }> = (props) => {
  return (
    <p class="text-4xl text-green-700 text-center py-20">{props.message}</p>
  );
};

const AlertDisplay: Component<{ message: string }> = (props) => {
  return (
    <p class="text-4xl text-green-700 text-center py-20">{props.message}</p>
  );
};

const ClockDisplay: Component<{ message: string }> = (props) => {
  return (
    <p class="text-4xl text-green-700 text-center py-20">{props.message}</p>
  );
};

const App: Component = () => {
  const handleSSEMessage = (event: MessageEvent) => {
    console.log("SSEMessage Received:", event.data);
  };

  const handleAlertSSEMessage = (event: MessageEvent) => {
    console.log("AlertSSEMessage Received:", event.data);
  };

  const setupSSE = () => {
    const sse = new EventSource("/events");
    sse.addEventListener("SSEMessage", handleSSEMessage);
    sse.addEventListener("AlertSSEMessage", handleSSEMessage);

    onCleanup(() => {
      sse.close();
    });
  };

  setupSSE();

  return (
    <p class="text-4xl text-green-700 text-center py-20">Hello tailwind!</p>
  );
};

export default App;

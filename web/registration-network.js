"use strict";

// Reading a one-time link is safe to retry. Saving a character is not.
const RegistrationNetwork = (() => {
  class RequestError extends Error {
    constructor(message, { status = 0, retryable = false } = {}) {
      super(message);
      this.status = status;
      this.retryable = retryable;
    }
  }

  async function request(url, options = {}, onRetry = () => {}) {
    const reading = (options.method || "GET").toUpperCase() === "GET";
    const attempts = reading ? 3 : 1;
    for (let attempt = 0; attempt < attempts; attempt++) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), reading ? 8000 : 30000);
      try {
        const response = await fetch(url, {
          ...options, cache: "no-store", referrerPolicy: "no-referrer", signal: controller.signal,
        });
        const data = await response.json().catch(() => null);
        if (!response.ok) {
          throw new RequestError(data?.error || data?.reason || `Сервер вернул ошибку ${response.status}.`, {
            status: response.status, retryable: response.status >= 500,
          });
        }
        if (!data) throw new RequestError("Сервер вернул неполный ответ.", { retryable: true });
        return data;
      } catch (error) {
        const temporary = !(error instanceof RequestError) || error.retryable;
        if (reading && temporary && attempt + 1 < attempts) {
          onRetry(attempt + 2, attempts);
          await new Promise(resolve => setTimeout(resolve, 900 * (attempt + 1)));
          continue;
        }
        if (error instanceof RequestError && !error.retryable) throw error;
        throw new RequestError(reading
          ? (error instanceof RequestError ? `${error.message} Нажмите «Повторить».`
            : "Не удалось связаться с сервером регистрации. Нажмите «Повторить». Если ошибка остаётся, попробуйте другую сеть или сообщите мастеру.")
          : "Не удалось получить подтверждение сохранения. Сначала проверьте /персонаж в Дискорде: персонаж мог уже сохраниться. Если его нет, повторите отправку. Анкета осталась на странице.",
          { retryable: true, status: error.status || 0 });
      } finally {
        clearTimeout(timer);
      }
    }
  }

  return { request };
})();

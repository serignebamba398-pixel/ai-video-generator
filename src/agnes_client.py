from __future__ import annotations

import base64
import json
import mimetypes
import time

from pathlib import Path
from typing import Callable, Optional

import requests

from src.config import (
    AGNES_API_KEY,
    AGNES_BASE_URL,
    AGNES_IMAGE_MODEL,
    AGNES_MODEL,
)


# ==========================================================
# EXCEPTION
# ==========================================================


class AgnesAPIError(Exception):

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        response_body: Optional[str] = None,
        retry_after: Optional[float] = None,
        retryable: bool = False,
    ) -> None:

        super().__init__(
            message
        )

        self.status_code = (
            status_code
        )

        self.error_code = (
            error_code
        )

        self.response_body = (
            response_body
        )

        self.retry_after = (
            retry_after
        )

        self.retryable = (
            retryable
        )


# ==========================================================
# AGNES CLIENT
# ==========================================================


class AgnesClient:

    def __init__(
        self,
        api_key: str = AGNES_API_KEY,
        base_url: str = AGNES_BASE_URL,
        model: str = AGNES_MODEL,
        image_model: str = (
            AGNES_IMAGE_MODEL
        ),
        timeout: int = 120,
    ) -> None:

        self.api_key = api_key
        self.base_url = (
            base_url.rstrip("/")
        )

        self.model = model
        self.image_model = (
            image_model
        )

        self.timeout = timeout

        self.headers = {
            "Authorization": (
                f"Bearer {self.api_key}"
            ),
            "Content-Type": (
                "application/json"
            ),
        }

        self.video_url = (
            f"{self.base_url}"
            "/v1/videos"
        )

        self.image_url = (
            f"{self.base_url}"
            "/v1/images/generations"
        )

        self.status_url = (
            f"{self.base_url}"
            "/agnesapi"
        )

    # ======================================================
    # MEDIA -> DATA URI
    # ======================================================

    @staticmethod
    def _file_to_data_uri(
        path: Path,
    ) -> str:

        path = Path(
            path
        )

        if not path.exists():

            raise AgnesAPIError(
                "Reference media file "
                f"does not exist: {path}"
            )

        if not path.is_file():

            raise AgnesAPIError(
                "Reference media path "
                f"is not a file: {path}"
            )

        mime_type, _ = (
            mimetypes.guess_type(
                str(path)
            )
        )

        if mime_type is None:

            suffix = (
                path.suffix.lower()
            )

            fallback = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
                ".mp3": "audio/mpeg",
                ".wav": "audio/wav",
                ".m4a": "audio/mp4",
            }

            mime_type = fallback.get(
                suffix,
                "application/octet-stream",
            )

        try:

            encoded = base64.b64encode(
                path.read_bytes()
            ).decode(
                "ascii"
            )

        except OSError as exc:

            raise AgnesAPIError(
                "Unable to read reference "
                f"media file: {path}"
            ) from exc

        return (
            f"data:{mime_type};"
            f"base64,{encoded}"
        )

    # ======================================================
    # GENERATE CHARACTER IMAGE
    # ======================================================

    def generate_image(
        self,
        prompt: str,
        output_path: Path,
        size: str = "1K",
        ratio: str = "3:4",
    ) -> Path:

        output_path = Path(
            output_path
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = {
            "model": (
                self.image_model
            ),
            "prompt": prompt,
            "n": 1,
            "size": size,
            "ratio": ratio,
        }

        try:

            response = requests.post(
                self.image_url,
                headers=self.headers,
                json=payload,
                timeout=self.timeout,
            )

        except requests.RequestException as exc:

            raise AgnesAPIError(
                "Agnes image request failed: "
                f"{exc}",
                retryable=True,
            ) from exc

        if not response.ok:

            raise self._build_http_error(
                response=response,
                prefix=(
                    "Agnes image generation failed."
                ),
            )

        try:

            data = response.json()

        except ValueError as exc:

            raise AgnesAPIError(
                "Agnes image API returned "
                "invalid JSON."
            ) from exc

        image_entry = None

        if isinstance(
            data,
            dict,
        ):

            entries = (
                data.get(
                    "data"
                )
            )

            if (
                isinstance(
                    entries,
                    list,
                )
                and entries
            ):

                image_entry = (
                    entries[0]
                )

        if not isinstance(
            image_entry,
            dict,
        ):

            raise AgnesAPIError(
                "Agnes image response "
                "contains no image."
            )

        image_url = (
            image_entry.get(
                "url"
            )
        )

        b64_json = (
            image_entry.get(
                "b64_json"
            )
        )

        if image_url:

            self._download_file(
                url=str(
                    image_url
                ),
                output_path=(
                    output_path
                ),
            )

            return output_path

        if b64_json:

            try:

                raw = (
                    base64.b64decode(
                        b64_json
                    )
                )

                output_path.write_bytes(
                    raw
                )

            except Exception as exc:

                raise AgnesAPIError(
                    "Unable to decode Agnes "
                    "image response."
                ) from exc

            return output_path

        raise AgnesAPIError(
            "Agnes image response contains "
            "neither URL nor Base64 image."
        )

    # ======================================================
    # TEXT VIDEO
    # ======================================================

    def create_video(
        self,
        prompt: str,
        seconds: int,
        size: str = "720P",
        aspect_ratio: str = "16:9",
        max_retries: int = 1,
        retry_delay: int = 30,
    ) -> str:

        payload = {
            "model": self.model,
            "prompt": prompt,
            "mode": "text",
            "seconds": str(
                seconds
            ),
            "size": size,
            "aspect_ratio": (
                aspect_ratio
            ),
            "n": 1,
        }

        return (
            self._submit_video_request(
                payload=payload,
                max_retries=(
                    max_retries
                ),
                retry_delay=(
                    retry_delay
                ),
            )
        )

    # ======================================================
    # REFERENCE VIDEO
    # ======================================================

    def create_reference_video(
        self,
        prompt: str,
        seconds: int,
        size: str = "720P",
        aspect_ratio: str = "16:9",
        image_paths: Optional[
            list[Path]
        ] = None,
        audio_paths: Optional[
            list[Path]
        ] = None,
        audio_path: Optional[
            Path
        ] = None,
        max_retries: int = 1,
        retry_delay: int = 30,
    ) -> str:

        """
        Reference mode.

        Supports:
        - image references only
        - audio reference only
        - images + audio simultaneously

        audio_path is retained for compatibility with
        older project code.
        """

        image_paths = list(
            image_paths
            or []
        )

        audio_paths = list(
            audio_paths
            or []
        )

        if (
            audio_path is not None
            and not audio_paths
        ):

            audio_paths.append(
                Path(
                    audio_path
                )
            )

        if len(
            image_paths
        ) > 5:

            raise AgnesAPIError(
                "Agnes Video 2.5 Flash accepts "
                "at most 5 reference images."
            )

        if len(
            audio_paths
        ) > 3:

            raise AgnesAPIError(
                "Agnes Video 2.5 Flash accepts "
                "at most 3 reference audios."
            )

        if (
            not image_paths
            and not audio_paths
        ):

            raise AgnesAPIError(
                "Reference mode requires at least "
                "one reference image or audio."
            )

        images = [
            self._file_to_data_uri(
                path
            )
            for path
            in image_paths
        ]

        audios = [
            self._file_to_data_uri(
                path
            )
            for path
            in audio_paths
        ]

        payload = {
            "model": self.model,
            "prompt": prompt,
            "mode": "reference",
            "seconds": str(
                seconds
            ),
            "size": size,
            "aspect_ratio": (
                aspect_ratio
            ),
            "n": 1,
        }

        if images:

            payload[
                "images"
            ] = images

        if audios:

            payload[
                "audios"
            ] = audios

        return (
            self._submit_video_request(
                payload=payload,
                max_retries=(
                    max_retries
                ),
                retry_delay=(
                    retry_delay
                ),
            )
        )

    # ======================================================
    # SUBMIT VIDEO
    # ======================================================

    def _submit_video_request(
        self,
        payload: dict,
        max_retries: int,
        retry_delay: int,
    ) -> str:

        max_retries = max(
            1,
            int(
                max_retries
            ),
        )

        last_error: Optional[
            AgnesAPIError
        ] = None

        for attempt in range(
            1,
            max_retries + 1,
        ):

            try:

                response = requests.post(
                    self.video_url,
                    headers=self.headers,
                    json=payload,
                    timeout=self.timeout,
                )

            except requests.RequestException as exc:

                error = AgnesAPIError(
                    "Unable to contact Agnes "
                    f"video API: {exc}",
                    retryable=True,
                )

                last_error = error

                if attempt >= max_retries:
                    raise error from exc

                time.sleep(
                    retry_delay
                )

                continue

            if not response.ok:

                error = (
                    self._build_http_error(
                        response=response,
                        prefix=(
                            "Agnes video "
                            "submission failed."
                        ),
                    )
                )

                last_error = error

                if (
                    not error.retryable
                    or attempt
                    >= max_retries
                ):

                    raise error

                time.sleep(
                    retry_delay
                )

                continue

            try:

                data = response.json()

            except ValueError as exc:

                raise AgnesAPIError(
                    "Agnes video submission "
                    "returned invalid JSON."
                ) from exc

            video_id = (
                self._extract_video_id(
                    data
                )
            )

            if not video_id:

                raise AgnesAPIError(
                    "Agnes accepted the request "
                    "but returned no video_id. "
                    f"Response: {data}"
                )

            return video_id

        if last_error:

            raise last_error

        raise AgnesAPIError(
            "Agnes video submission failed."
        )

    # ======================================================
    # VIDEO STATUS
    # ======================================================

    def get_video_status(
        self,
        video_id: str,
    ) -> dict:

        try:

            response = requests.get(
                self.status_url,
                headers=self.headers,
                params={
                    "video_id": (
                        video_id
                    ),
                    "model_name": (
                        self.model
                    ),
                },
                timeout=self.timeout,
            )

        except requests.RequestException as exc:

            raise AgnesAPIError(
                "Unable to retrieve Agnes "
                f"video status: {exc}",
                retryable=True,
            ) from exc

        if not response.ok:

            raise self._build_http_error(
                response=response,
                prefix=(
                    "Agnes video status "
                    "request failed."
                ),
            )

        try:

            return response.json()

        except ValueError as exc:

            raise AgnesAPIError(
                "Agnes status endpoint "
                "returned invalid JSON."
            ) from exc

    # ======================================================
    # WAIT FOR VIDEO
    # ======================================================

    def wait_for_video(
        self,
        video_id: str,
        polling_interval: int = 5,
        timeout: int = 1800,
        progress_callback: Optional[
            Callable[
                [
                    str,
                    int,
                ],
                None,
            ]
        ] = None,
    ) -> str:

        started = (
            time.monotonic()
        )

        while True:

            if (
                time.monotonic()
                - started
                > timeout
            ):

                raise AgnesAPIError(
                    "Timed out while waiting "
                    "for Agnes video generation."
                )

            try:

                data = (
                    self.get_video_status(
                        video_id
                    )
                )

            except AgnesAPIError as exc:

                if (
                    exc.retryable
                    or exc.status_code
                    in {
                        429,
                        500,
                        502,
                        503,
                        504,
                    }
                ):

                    time.sleep(
                        polling_interval
                    )

                    continue

                raise

            status = str(
                data.get(
                    "status",
                    "",
                )
                or ""
            ).lower()

            progress = (
                data.get(
                    "progress",
                    0,
                )
            )

            try:

                progress = int(
                    progress
                )

            except (
                TypeError,
                ValueError,
            ):

                progress = 0

            if progress_callback:

                progress_callback(
                    status or "pending",
                    progress,
                )

            if (
                status
                == "completed"
            ):

                video_url = (
                    self._extract_video_url(
                        data
                    )
                )

                if not video_url:

                    raise AgnesAPIError(
                        "Agnes marked the video "
                        "completed but returned "
                        "no download URL."
                    )

                return video_url

            if status in {
                "failed",
                "cancelled",
                "canceled",
                "rejected",
            }:

                message = (
                    self._extract_message(
                        data
                    )
                )

                error_code = (
                    self._extract_error_code(
                        data
                    )
                )

                try:
                    response_detail = json.dumps(
                        data,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                except (TypeError, ValueError):
                    response_detail = str(data)

                raise AgnesAPIError(
                    "Agnes video task failed. "
                    f"status={status}"
                    + (
                        f" | error_code={error_code}"
                        if error_code
                        else ""
                    )
                    + (
                        f" | message={message}"
                        if message
                        else ""
                    )
                    + f" | response={response_detail}",
                    error_code=error_code,
                    response_body=response_detail,
                    retryable=status == "failed",
                )

            time.sleep(
                polling_interval
            )

    # ======================================================
    # DOWNLOAD VIDEO
    # ======================================================

    def download_video(
        self,
        video_url: str,
        output_path: Path,
    ) -> Path:

        output_path = Path(
            output_path
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._download_file(
            url=video_url,
            output_path=output_path,
        )

        return output_path

    # ======================================================
    # GENERIC DOWNLOAD
    # ======================================================

    def _download_file(
        self,
        url: str,
        output_path: Path,
    ) -> None:

        try:

            with requests.get(
                url,
                stream=True,
                timeout=300,
            ) as response:

                if not response.ok:

                    raise self._build_http_error(
                        response=response,
                        prefix=(
                            "Media download failed."
                        ),
                    )

                with output_path.open(
                    "wb"
                ) as file_handle:

                    for chunk in (
                        response.iter_content(
                            chunk_size=(
                                1024 * 1024
                            )
                        )
                    ):

                        if chunk:

                            file_handle.write(
                                chunk
                            )

        except AgnesAPIError:
            raise

        except requests.RequestException as exc:

            raise AgnesAPIError(
                "Unable to download Agnes "
                f"media: {exc}",
                retryable=True,
            ) from exc

        except OSError as exc:

            raise AgnesAPIError(
                "Unable to save Agnes media "
                f"to {output_path}: {exc}"
            ) from exc

    # ======================================================
    # RESPONSE PARSERS
    # ======================================================

    @staticmethod
    def _extract_video_id(
        data,
    ) -> Optional[str]:

        if isinstance(
            data,
            dict,
        ):

            for key in (
                "video_id",
                "id",
                "task_id",
            ):

                value = (
                    data.get(
                        key
                    )
                )

                if value:

                    return str(
                        value
                    )

            for key in (
                "data",
                "result",
            ):

                nested = (
                    data.get(
                        key
                    )
                )

                found = (
                    AgnesClient
                    ._extract_video_id(
                        nested
                    )
                )

                if found:
                    return found

        if isinstance(
            data,
            list,
        ):

            for item in data:

                found = (
                    AgnesClient
                    ._extract_video_id(
                        item
                    )
                )

                if found:
                    return found

        return None

    @staticmethod
    def _extract_video_url(
        data,
    ) -> Optional[str]:

        if isinstance(
            data,
            dict,
        ):

            for key in (
                "url",
                "video_url",
                "download_url",
            ):

                value = (
                    data.get(
                        key
                    )
                )

                if (
                    isinstance(
                        value,
                        str,
                    )
                    and value.startswith(
                        "http"
                    )
                ):

                    return value

            for key in (
                "data",
                "result",
                "output",
            ):

                nested = (
                    data.get(
                        key
                    )
                )

                found = (
                    AgnesClient
                    ._extract_video_url(
                        nested
                    )
                )

                if found:
                    return found

        if isinstance(
            data,
            list,
        ):

            for item in data:

                found = (
                    AgnesClient
                    ._extract_video_url(
                        item
                    )
                )

                if found:
                    return found

        return None

    @staticmethod
    def _extract_message(
        data,
    ) -> str:

        if isinstance(
            data,
            dict,
        ):

            for key in (
                "message",
                "error",
                "detail",
            ):

                value = (
                    data.get(
                        key
                    )
                )

                if isinstance(
                    value,
                    str,
                ):

                    return value

                nested_message = (
                    AgnesClient._extract_message(
                        value
                    )
                )

                if nested_message:
                    return nested_message

            for value in data.values():
                nested_message = (
                    AgnesClient._extract_message(
                        value
                    )
                )

                if nested_message:
                    return nested_message

        if isinstance(
            data,
            list,
        ):

            for value in data:
                nested_message = (
                    AgnesClient._extract_message(
                        value
                    )
                )

                if nested_message:
                    return nested_message

        return ""

    @staticmethod
    def _extract_error_code(
        data,
    ) -> str:

        if isinstance(
            data,
            dict,
        ):

            for key in (
                "code",
                "error_code",
                "errorCode",
            ):

                value = data.get(key)

                if isinstance(value, (str, int, float)):
                    return str(value)

            for value in data.values():
                nested_code = (
                    AgnesClient._extract_error_code(
                        value
                    )
                )

                if nested_code:
                    return nested_code

        if isinstance(
            data,
            list,
        ):

            for value in data:
                nested_code = (
                    AgnesClient._extract_error_code(
                        value
                    )
                )

                if nested_code:
                    return nested_code

        return ""

    # ======================================================
    # HTTP ERROR
    # ======================================================

    @staticmethod
    def _build_http_error(
        response: requests.Response,
        prefix: str,
    ) -> AgnesAPIError:

        status_code = (
            response.status_code
        )

        response_body = (
            response.text
            or ""
        )

        retry_after = None

        retry_header = (
            response.headers.get(
                "Retry-After"
            )
        )

        if retry_header:

            try:

                retry_after = float(
                    retry_header
                )

            except ValueError:
                retry_after = None

        error_code = None
        message = None

        try:

            data = response.json()

            if isinstance(
                data,
                dict,
            ):

                error_code = (
                    data.get(
                        "code"
                    )
                    or data.get(
                        "error_code"
                    )
                )

                raw_message = (
                    data.get(
                        "message"
                    )
                    or data.get(
                        "error"
                    )
                    or data.get(
                        "detail"
                    )
                )

                if isinstance(
                    raw_message,
                    dict,
                ):

                    message = (
                        raw_message.get(
                            "message"
                        )
                        or str(
                            raw_message
                        )
                    )

                elif raw_message:

                    message = str(
                        raw_message
                    )

        except ValueError:
            pass

        if not message:

            message = (
                response.reason
                or response_body
                or "Unknown Agnes error"
            )

        retryable = (
            status_code == 429
            or status_code
            in {
                408,
                425,
                500,
                502,
                503,
                504,
            }
        )

        full_message = (
            f"{prefix}"
            f" | HTTP {status_code}"
        )

        if error_code:

            full_message += (
                f" | error_code="
                f"{error_code}"
            )

        if message:

            full_message += (
                f" | message="
                f"{message}"
            )

        if response_body:

            full_message += (
                " | response_body="
                f"{response_body}"
            )

        return AgnesAPIError(
            message=full_message,
            status_code=(
                status_code
            ),
            error_code=(
                str(error_code)
                if error_code
                else None
            ),
            response_body=(
                response_body
            ),
            retry_after=(
                retry_after
            ),
            retryable=(
                retryable
            ),
        )

import fnmatch
import platform
import time
import logging
import os
import re
from filelock import SoftFileLock
import requests
from typing import List, Optional, Tuple, Union
from pathlib import Path
from tqdm import tqdm
from tqdm.contrib.concurrent import thread_map

from huggingface_hub import HfApi, hf_hub_download, snapshot_download
from modelscope.hub.api import HubApi
from modelscope.hub.snapshot_download import (
    snapshot_download as modelscope_snapshot_download,
)
from modelscope.hub.utils.utils import model_id_to_group_owner_name
import base64
import random
import string
import hashlib
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from gpustack.schemas.models import Model, ModelSource, SourceEnum, get_mmproj_filename
from gpustack.utils import file
from gpustack.utils.hub import match_hugging_face_files, match_model_scope_file_paths

logger = logging.getLogger(__name__)


def download_model(
    model: ModelSource,
    local_dir: Optional[str] = None,
    cache_dir: Optional[str] = None,
    ollama_library_base_url: Optional[str] = None,
    huggingface_token: Optional[str] = None,
) -> List[str]:
    if model.source == SourceEnum.HUGGING_FACE:
        return HfDownloader.download(
            repo_id=model.huggingface_repo_id,
            filename=model.huggingface_filename,
            extra_filename=get_mmproj_filename(model),
            token=huggingface_token,
            local_dir=local_dir,
            cache_dir=os.path.join(cache_dir, "huggingface"),
        )
    elif model.source == SourceEnum.OLLAMA_LIBRARY:
        ollama_downloader = OllamaLibraryDownloader(
            registry_url=ollama_library_base_url
        )
        return ollama_downloader.download(
            model_name=model.ollama_library_model_name,
            local_dir=local_dir,
            cache_dir=os.path.join(cache_dir, "ollama"),
        )
    elif model.source == SourceEnum.MODEL_SCOPE:
        return ModelScopeDownloader.download(
            model_id=model.model_scope_model_id,
            file_path=model.model_scope_file_path,
            extra_file_path=get_mmproj_filename(model),
            local_dir=local_dir,
            cache_dir=os.path.join(cache_dir, "model_scope"),
        )
    elif model.source == SourceEnum.LOCAL_PATH:
        return file.get_sharded_file_paths(model.local_path)


def get_model_file_size(
    model: Model,
    huggingface_token: Optional[str] = None,
    cache_dir: Optional[str] = None,
    ollama_library_base_url: Optional[str] = None,
) -> Optional[int]:
    if model.source == SourceEnum.HUGGING_FACE:
        return HfDownloader.get_model_file_size(
            model=model,
            token=huggingface_token,
        )
    elif model.source == SourceEnum.MODEL_SCOPE:
        return ModelScopeDownloader.get_model_file_size(
            model=model,
        )
    elif model.source == SourceEnum.OLLAMA_LIBRARY:
        ollama_downloader = OllamaLibraryDownloader(
            registry_url=ollama_library_base_url
        )
        return ollama_downloader.get_model_file_size(
            model_name=model.ollama_library_model_name,
            cache_dir=os.path.join(cache_dir, "ollama"),
        )
    elif model.source == SourceEnum.LOCAL_PATH:
        return file.getsize(model.local_path)

    raise ValueError(f"Unsupported model source: {model.source}")


class HfDownloader:
    _registry_url = "https://huggingface.co"

    @classmethod
    def get_file_size(
        cls,
        repo_id: str,
        filename: str,
        token: Optional[str],
        extra_filename: Optional[str] = None,
    ) -> int:
        api = HfApi(token=token)
        repo_info = api.repo_info(repo_id, files_metadata=True)
        total_size = sum(
            sibling.size
            for sibling in repo_info.siblings
            if (
                not filename
                or fnmatch.fnmatch(sibling.rfilename, filename)
                or (
                    extra_filename
                    and fnmatch.fnmatch(sibling.rfilename, extra_filename)
                )
            )
            and sibling.size is not None
        )

        return total_size

    @classmethod
    def get_model_file_size(cls, model: Model, token: Optional[str]) -> int:

        return HfDownloader.get_file_size(
            repo_id=model.huggingface_repo_id,
            filename=model.huggingface_filename,
            extra_filename=get_mmproj_filename(model),
            token=token,
        )

    @classmethod
    def download(
        cls,
        repo_id: str,
        filename: Optional[str],
        extra_filename: Optional[str],
        token: Optional[str] = None,
        local_dir: Optional[Union[str, os.PathLike[str]]] = None,
        cache_dir: Optional[Union[str, os.PathLike[str]]] = None,
        max_workers: int = 8,
    ) -> List[str]:
        """Download a model from the Hugging Face Hub.

        Args:
            repo_id:
                The model repo id.
            filename:
                A filename or glob pattern to match the model file in the repo.
            token:
                The Hugging Face API token.
            local_dir:
                The local directory to save the model to.
            local_dir_use_symlinks:
                Whether to use symlinks when downloading the model.
            max_workers (`int`, *optional*):
                Number of concurrent threads to download files (1 thread = 1 file download).
                Defaults to 8.

        Returns:
            The paths to the downloaded model files.
        """

        group_or_owner, name = model_id_to_group_owner_name(repo_id)
        lock_filename = os.path.join(cache_dir, group_or_owner, f"{name}.lock")

        if local_dir is None:
            local_dir = os.path.join(cache_dir, group_or_owner, name)

        logger.info(f"Retriving file lock: {lock_filename}")
        with SoftFileLock(lock_filename):
            if filename:
                return cls.download_file(
                    repo_id=repo_id,
                    filename=filename,
                    token=token,
                    local_dir=local_dir,
                    extra_filename=extra_filename,
                )

            snapshot_download(
                repo_id=repo_id,
                token=token,
                local_dir=local_dir,
            )
            return [local_dir]

    @classmethod
    def download_file(
        cls,
        repo_id: str,
        filename: Optional[str],
        token: Optional[str] = None,
        local_dir: Optional[Union[str, os.PathLike[str]]] = None,
        max_workers: int = 8,
        extra_filename: Optional[str] = None,
    ) -> List[str]:
        """Download a model from the Hugging Face Hub.
        Args:
            repo_id: The model repo id.
            filename: A filename or glob pattern to match the model file in the repo.
            token: The Hugging Face API token.
            local_dir: The local directory to save the model to.
            local_dir_use_symlinks: Whether to use symlinks when downloading the model.
        Returns:
            The path to the downloaded model.
        """

        matching_files = match_hugging_face_files(
            repo_id, filename, extra_filename, token
        )

        if len(matching_files) == 0:
            raise ValueError(f"No file found in {repo_id} that match {filename}")

        logger.info(f"Downloading model {repo_id}/{filename}")

        subfolder = (
            None
            if (subfolder := str(Path(matching_files[0]).parent)) == "."
            else subfolder
        )

        unfolder_matching_files = [Path(file).name for file in matching_files]
        downloaded_files = []

        def _inner_hf_hub_download(repo_file: str):
            downloaded_file = hf_hub_download(
                repo_id=repo_id,
                filename=repo_file,
                token=token,
                subfolder=subfolder,
                local_dir=local_dir,
            )
            downloaded_files.append(downloaded_file)

        thread_map(
            _inner_hf_hub_download,
            unfolder_matching_files,
            desc=f"Fetching {len(unfolder_matching_files)} files",
            max_workers=max_workers,
        )

        logger.info(f"Downloaded model {repo_id}/{filename}")
        return sorted(downloaded_files)

    def __call__(self):
        return self.download()


_header_user_agent = "User-Agent"
_header_authorization = "Authorization"
_header_accept = "Accept"
_header_www_authenticate = "WWW-Authenticate"


class OllamaLibraryDownloader:
    _default_cache_dir = "/var/lib/gpustack/cache/ollama"
    _user_agent = f"ollama/0.3.3 ({platform.machine()} {platform.system()}) Go/1.22.0"

    def __init__(
        self,
        registry_url: Optional[str] = "https://registry.ollama.ai",
    ):
        self._registry_url = registry_url

    def download_blob(
        self, url: str, registry_token: str, filename: str, _nb_retries: int = 5
    ):
        temp_filename = filename + ".part"

        headers = {
            _header_user_agent: self._user_agent,
            _header_authorization: registry_token,
        }

        if os.path.exists(temp_filename):
            existing_file_size = os.path.getsize(temp_filename)
            headers["Range"] = f"bytes={existing_file_size}-"
        else:
            existing_file_size = 0

        response = requests.get(url, headers=headers, stream=True)
        total_size = int(response.headers.get("content-length", 0)) + existing_file_size

        mode = "ab" if existing_file_size > 0 else "wb"
        chunk_size = 10 * 1024 * 1024  # 10MB
        with (
            open(temp_filename, mode) as file,
            tqdm(
                total=total_size,
                initial=existing_file_size,
                unit='B',
                unit_scale=True,
                unit_divisor=1024,
                desc=os.path.basename(filename),
            ) as bar,
        ):
            try:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        file.write(chunk)
                        bar.update(len(chunk))

                        _nb_retries = 5
            except Exception as e:
                if _nb_retries <= 0:
                    logger.warning(
                        "Error while downloading model: %s\nMax retries exceeded.",
                        str(e),
                    )
                    raise
                logger.warning(
                    "Error while downloading model: %s\nTrying to resume download...",
                    str(e),
                )
                time.sleep(1)
                return self.download_blob(
                    url, registry_token, filename, _nb_retries - 1
                )
        os.rename(temp_filename, filename)

    def download(
        self,
        model_name: str,
        local_dir: Optional[str] = None,
        cache_dir: Optional[str] = None,
    ) -> List[str]:
        sanitized_filename = re.sub(r"[^a-zA-Z0-9]", "_", model_name)

        if cache_dir is None:
            cache_dir = self._default_cache_dir

        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)

        if local_dir and not os.path.exists(local_dir):
            os.makedirs(local_dir)

        model_dir = local_dir
        if local_dir is None:
            model_dir = cache_dir

        model_path = os.path.join(model_dir, sanitized_filename)
        lock_filename = model_path + ".lock"

        logger.info(f"Retriving file lock: {lock_filename}")
        with SoftFileLock(lock_filename):
            if os.path.exists(model_path):
                return [model_path]

            logger.info(f"Downloading model {model_name}")
            blob_url, registry_token = self.model_url(
                model_name=model_name, cache_dir=cache_dir
            )
            if blob_url is not None:
                self.download_blob(blob_url, registry_token, model_path)

            logger.info(f"Downloaded model {model_name}")
            return [model_path]

    def get_model_file_size(
        self, model_name: str, cache_dir: Optional[str] = None
    ) -> int:

        if cache_dir is None:
            cache_dir = self._default_cache_dir

        blob_url, registry_token = self.model_url(
            model_name=model_name, cache_dir=cache_dir
        )
        if blob_url is not None:
            response = requests.head(
                blob_url, headers={_header_authorization: registry_token}
            )
            if response.status_code == 200:
                return int(response.headers.get("content-length", 0))

        return 0

    def model_url(self, model_name: str, cache_dir: Optional[str] = None) -> str:
        repo, tag = self.parse_model_name(model_name)

        manifest_url = f"{self._registry_url}/v2/{repo}/manifests/{tag}"

        headers = {
            _header_user_agent: self._user_agent,
            _header_accept: "application/vnd.docker.distribution.manifest.v2+json",
        }

        response = None
        token = None
        for i in range(2):
            response = requests.get(manifest_url, headers=headers)
            if response.status_code == 200:
                break
            elif response.status_code == 401:
                logger.debug("ollama registry requires authorization")

                token = self.get_request_auth_token(manifest_url, cache_dir)
                if token:
                    headers[_header_authorization] = token
                else:
                    logger.warning("Failed to get ollama registry token")
            else:
                raise Exception(
                    f"Failed to download model {model_name}, status code: {response.status_code}"
                )

        manifest = response.json()
        blobs = manifest.get("layers", [])

        for blob in blobs:
            if blob["mediaType"] == "application/vnd.ollama.image.model":
                return (
                    f"{self._registry_url}/v2/{repo}/blobs/{blob['digest']}",
                    token,
                )

        return None

    @staticmethod
    def parse_model_name(model_name: str) -> Tuple[str, str]:
        if ":" in model_name:
            repo, tag = model_name.split(":")
        else:
            repo, tag = model_name, "latest"

        if "/" not in repo:
            repo = "library/" + repo

        return repo, tag

    @classmethod
    def get_request_auth_token(cls, request_url, cache_dir: Optional[str] = None):

        response = requests.get(
            request_url, headers={_header_user_agent: cls._user_agent}
        )

        if response.status_code != 401 or response.request is None:
            logger.debug(
                f"ollama response status code from {request_url}: {response.status_code}"
            )
            return None

        request = response.request
        if _header_authorization in request.headers:
            # Already authorized.
            return request.headers[_header_authorization]

        authn_token = response.headers.get(_header_www_authenticate, '').replace(
            'Bearer ', ''
        )

        if not authn_token:
            logger.debug("ollama WWW-Authenticate header not found")
            return None

        authz_token = cls.get_registry_auth_token(authn_token, cache_dir)
        if not authz_token:
            logger.debug("ollama registry authorize failed")
            return None

        return f"Bearer {authz_token}"

    @classmethod
    def get_registry_auth_token(cls, authn_token, cache_dir: Optional[str] = None):
        pri_key = cls.load_sing_key(cache_dir)
        if not pri_key:
            return None

        parts = authn_token.split(',')
        if len(parts) < 3:
            return None

        realm, service, scope = None, None, None
        for part in parts:
            key, value = part.split('=')
            value = value.strip('"\'')
            if key == 'realm':
                realm = value
            elif key == 'service':
                service = value
            elif key == 'scope':
                scope = value

        if not realm or not service or not scope:
            logger.debug("not all required parts found in WWW-Authenticate header")
            return None

        authz_url = f"{realm}?nonce={''.join(random.choices(string.ascii_letters + string.digits, k=16))}&scope={scope}service={service}&ts={int(time.time())}"

        pub_key = (
            pri_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.OpenSSH,
                format=serialization.PublicFormat.OpenSSH,
            )
            .split()[1]
        )

        sha = hashlib.sha256(b'').hexdigest()
        sha_bytes = sha.encode()
        nc = base64.b64encode(sha_bytes).decode()

        py = f"GET,{authz_url},{nc}".encode()
        sd = pri_key.sign(py)
        authn_data = f"{pub_key.decode()}:{base64.b64encode(sd).decode()}"

        headers = {_header_authorization: authn_data}
        response = requests.get(authz_url, headers=headers)
        if response.status_code != 200:
            logger.debug(f"ollama registry authorize failed: {response.status_code}")
            return None

        token_data = response.json()
        return token_data.get('token')

    @classmethod
    def load_sing_key(cls, cache_dir: Optional[str] = None):
        key_dir = os.path.join(cache_dir, ".ollama")
        pri_key_path = os.path.join(key_dir, "id_ed25519")

        if not os.path.exists(pri_key_path):
            os.makedirs(key_dir, exist_ok=True)
            pri_key = ed25519.Ed25519PrivateKey.generate()
            pub_key = pri_key.public_key()

            pri_key_bytes = pri_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.OpenSSH,
                encryption_algorithm=serialization.NoEncryption(),
            )

            pub_key_bytes = pub_key.public_bytes(
                encoding=serialization.Encoding.OpenSSH,
                format=serialization.PublicFormat.OpenSSH,
            )

            with open(pri_key_path, 'wb') as f:
                f.write(pri_key_bytes)
            with open(pri_key_path + ".pub", 'wb') as f:
                f.write(pub_key_bytes)
        else:
            with open(pri_key_path, 'rb') as f:
                pri_key_bytes = f.read()

            pri_key = serialization.load_ssh_private_key(
                pri_key_bytes, password=None, backend=default_backend()
            )

        return pri_key


class ModelScopeDownloader:

    @classmethod
    def get_file_size(
        cls,
        model_id: str,
        file_path: Optional[str],
        extra_file_path: Optional[str] = None,
    ) -> int:
        api = HubApi()
        repo_files = api.get_model_files(model_id, recursive=True)
        total_size = sum(
            sibling.get("Size")
            for sibling in repo_files
            if (
                not file_path
                or fnmatch.fnmatch(sibling.get("Path", ""), file_path)
                or (
                    extra_file_path
                    and fnmatch.fnmatch(sibling.get("Path", ""), extra_file_path)
                )
            )
            and "Size" in sibling
        )

        return total_size

    @classmethod
    def get_model_file_size(cls, model: Model) -> int:
        return ModelScopeDownloader.get_file_size(
            model_id=model.model_scope_model_id,
            file_path=model.model_scope_file_path,
            extra_file_path=get_mmproj_filename(model),
        )

    @classmethod
    def download(
        cls,
        model_id: str,
        file_path: Optional[str],
        extra_file_path: Optional[str],
        local_dir: Optional[Union[str, os.PathLike[str]]] = None,
        cache_dir: Optional[Union[str, os.PathLike[str]]] = None,
    ) -> List[str]:
        """Download a model from Model Scope.

        Args:
            model_id:
                The model id.
            file_path:
                A filename or glob pattern to match the model file in the repo.
            cache_dir:
                The cache directory to save the model to.

        Returns:
            The path to the downloaded model.
        """

        group_or_owner, name = model_id_to_group_owner_name(model_id)
        lock_filename = os.path.join(cache_dir, group_or_owner, f"{name}.lock")

        logger.info("Retriving file lock")
        with SoftFileLock(lock_filename):
            if file_path:
                matching_files = match_model_scope_file_paths(
                    model_id, file_path, extra_file_path
                )
                if len(matching_files) == 0:
                    raise ValueError(
                        f"No file found in {model_id} that match {file_path}"
                    )

                model_dir = modelscope_snapshot_download(
                    model_id=model_id,
                    local_dir=local_dir,
                    cache_dir=cache_dir,
                    allow_patterns=matching_files,
                )
                return [os.path.join(model_dir, file) for file in matching_files]

            return [
                modelscope_snapshot_download(
                    model_id=model_id,
                    local_dir=local_dir,
                    cache_dir=cache_dir,
                )
            ]

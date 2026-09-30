import time
from urllib.parse import urlencode
from .common import PublishError, base_url, inside, secret
from .transport import Http, RemoteError, basic


class WordPressMedia:
    def __init__(self, config, state, folder, namespace, sleeper=time.sleep):
        self.url = base_url(config["media"]["url"], config.get("allow_local_http", False)) + "/wp-json/wp/v2/media"
        self.state, self.folder, self.namespace, self.sleeper = state, folder, namespace, sleeper
        media = config["media"]
        self.http = Http({"Authorization": basic(secret(media, "username_env"), secret(media, "password_env"))}, sleeper=sleeper)

    def find(self, slug):
        rows = self.http.request("GET", self.url + "?" + urlencode({"slug": slug, "per_page": 100}))
        matches = [r for r in rows if r.get("slug") == slug]
        if len(matches) > 1:
            raise PublishError("图片库存在重复标识，请核对图片库后重试")
        return matches[0] if matches else None

    def upload(self, asset):
        slug = "pandao-" + asset["sha256"]
        key = self.namespace + ":media:" + slug
        record = self.state.get(key)
        remote = self.find(slug)
        if remote:
            result = {"id": remote["id"], "url": remote["source_url"]}
            self.state.set(key, {"phase": "done", **result})
            return result
        if record.get("phase") in {"uploading", "uncertain", "done"}:
            raise PublishError("上次图片上传结果无法核实，请在图片库中核对；工具已停止重复上传")
        self.state.set(key, {"phase": "uploading"})
        try:
            remote = self.http.request("POST", self.url + "?" + urlencode({"slug": slug}),
                                       inside(self.folder, asset["file"]).read_bytes(),
                                       {"Content-Type": "image/jpeg", "Content-Disposition": f'attachment; filename="{slug}.jpg"'})
        except RemoteError as exc:
            if exc.ambiguous:
                for delay in (1, 2, 4):
                    self.sleeper(delay)
                    remote = self.find(slug)
                    if remote:
                        break
                else:
                    self.state.set(key, {"phase": "uncertain"})
                    raise
            else:
                self.state.set(key, {"phase": "failed"})
                raise
        # 上传回执之外，再读一次图片库；不从本机路径构造公开图片地址。
        verified = self.http.request("GET", self.url + "/" + str(remote["id"]))
        if verified.get("slug") != slug or not verified.get("source_url"):
            raise PublishError("图片上传后核对未通过，请检查图片库")
        result = {"id": verified["id"], "url": verified["source_url"]}
        self.state.set(key, {"phase": "done", **result})
        return result

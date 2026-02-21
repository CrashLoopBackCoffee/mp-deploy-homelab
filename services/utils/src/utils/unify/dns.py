import logging
import typing as t

import httpx
import pulumi as p

from utils.unify.api import UnifyApiDnsRecord

logging.basicConfig(format='%(asctime)s %(levelname)s %(name)s %(message)s', level=logging.WARNING)
logger = logging.getLogger(__name__)


class DnsRecordNotFoundError(RuntimeError):
    """The searched DNS record was not found in the device configuration."""


class UnifyDnsRecordProvider(p.dynamic.ResourceProvider):
    def __init__(self, *, base_url: str, api_token: str, verify_ssl: bool):
        super().__init__()
        self.base_url = base_url
        self.verify_ssl = verify_ssl
        self.headers = {
            'Content-Type': 'application/json',
            'X-API-KEY': api_token,
        }

    def client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            headers=self.headers,
            verify=self.verify_ssl,
        )

    @t.override
    def create(self, props: dict[str, t.Any]) -> p.dynamic.CreateResult:
        with self.client() as client:
            response = client.post(
                'proxy/network/v2/api/site/default/static-dns',
                json={
                    'record_type': 'A',
                    'key': props['domain_name'],
                    'value': props['ipv4'],
                    'enabled': True,
                },
            )

            if response.is_error:
                logger.error(response.json())
                response.raise_for_status()

            dns_record = UnifyApiDnsRecord.model_validate(response.json())
            assert dns_record.object_id, 'API objects have an ID'

        return p.dynamic.CreateResult(id_=dns_record.object_id, outs=dns_record.model_dump())

    @t.override
    def delete(self, _id: str, _props: dict[str, t.Any]):
        with self.client() as client:
            response = client.delete(f'proxy/network/v2/api/site/default/static-dns/{_id}')

            if response.is_error:
                logger.error(response.json())
                response.raise_for_status()

    @t.override
    def update(
        self, _id: str, _olds: dict[str, t.Any], _news: dict[str, t.Any]
    ) -> p.dynamic.UpdateResult:
        with self.client() as client:
            response = client.put(
                f'proxy/network/v2/api/site/default/static-dns/{_id}',
                json={
                    'record_type': 'A',
                    'key': _news['domain_name'],
                    'value': _news['ipv4'],
                    'enabled': True,
                },
            )

            if response.is_error:
                logger.error(response.json())
                response.raise_for_status()

        return p.dynamic.UpdateResult(outs=_news)

    @t.override
    def read(self, id_: str, props: dict[str, t.Any]) -> p.dynamic.ReadResult:
        with self.client() as client:
            response = client.get('proxy/network/v2/api/site/default/static-dns')

            if response.is_error:
                logger.error(response.json())
                response.raise_for_status()

        for dns_record_dict in response.json():
            dns_record = UnifyApiDnsRecord.model_validate(dns_record_dict)
            if dns_record.object_id == id_:
                return p.dynamic.ReadResult(id_=id_, outs=dns_record.model_dump())

        # not found:
        raise DnsRecordNotFoundError(id_, props)


class UnifyDnsRecord(p.dynamic.Resource):
    domain_name: p.Output[str]
    ipv4: p.Output[str]

    def __init__(
        self,
        name: str,
        *,
        domain_name: p.Input[str],
        ipv4: p.Input[str],
        provider: UnifyDnsRecordProvider,
        opts: p.ResourceOptions | None = None,
    ) -> None:
        super().__init__(
            provider,
            name,
            {'domain_name': domain_name, 'ipv4': ipv4},
            opts,
        )

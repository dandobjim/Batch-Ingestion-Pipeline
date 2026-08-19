with source as (select *
                from {{ source('raw', 'github_issues') }}),

     deduped as (select *,
                        row_number() over (
            partition by id
            order by _loaded_at desc
        ) as rn
                 from source),

     renamed as (select id                         as issue_id,
                        node_id                    as issue_node_id,
                        number                     as issue_number,
                        title,
                        body                       as issue_body,
                        state,
                        state_reason,
                        locked,
                        draft                      as is_draft,
                        (pull_request is not null) as is_pull_request,
                        author_association,
                        active_lock_reason,
                        comments                   as comments_count,

                        ("user" ->>'id')::bigint   as author_id,
                         "user" ->>'login'         as author_login,
                        (assignee->>'id')::bigint  as assignee_id,
                        assignee->>'login'         as assignee_login,
                        (closed_by->>'id')::bigint as closed_by_id,
                        closed_by->>'login'        as closed_by_login,
                        (milestone->>'id')::bigint as milestone_id,
                        milestone->>'title'        as milestone_title,
                        (reactions->>'total_count')::bigint as reactions_total_count,
                        (sub_issues_summary->>'total')::bigint as sub_issues_total,

                        labels as labels_json,
                        assignees as assignees_json,
                        created_at,
                        updated_at,
                        closed_at,
                        ingestion_date,
                        _loaded_at

from deduped
where rn = 1
    )

select *
from renamed